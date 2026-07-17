"""Backtest run contract loader and validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, cast

import yaml

from vertex.config.backfill import iter_backfill_dates, parse_backfill_date
from vertex.config.forecast_contract import ForecastContract, load_forecast_contract
from vertex.config.load_config import load_model_config
from vertex.utils.bigquery_utils import validate_bq_table_id
from vertex.utils.data_utils import get_hash

DEFAULT_BACKTEST_CONTRACT_PATH = Path(__file__).resolve().parent / "backtest_contract.yaml"

ALLOWED_BASELINES = frozenset(
    {
        "zero_demand",
        "last_observation",
        "seasonal_naive_7d",
        "same_period_last_year",
        "moving_average",
        "croston_sba_tsb",
    }
)
ALLOWED_METRICS = frozenset(
    {
        "wape",
        "mae",
        "mase",
        "rmsse",
        "bias",
        "pinball_loss",
        "interval_coverage",
        "interval_width",
        "prediction_completeness",
    }
)


@dataclass(frozen=True)
class BacktestContract:
    """Validated rolling-origin backtest contract."""

    raw: dict[str, Any]
    forecast_contract: ForecastContract
    origins: tuple[date, ...]

    @property
    def spec(self) -> dict[str, Any]:
        return cast(dict[str, Any], self.raw["backtest"])

    @property
    def name(self) -> str:
        return str(self.spec["name"])

    @property
    def hash(self) -> str:
        return get_hash(self.raw)

    @property
    def model_config_name(self) -> str:
        return str(self.spec["model_config_name"])

    @property
    def horizons(self) -> list[int]:
        return list(self.spec["horizons"])

    @property
    def train_window_days(self) -> int:
        return int(self.spec["train_window_days"])

    @property
    def segment_columns(self) -> list[str]:
        return list(self.spec.get("segment_columns") or [])

    @property
    def entity_columns(self) -> list[str]:
        return list(self.spec["entity_columns"])

    @property
    def date_column(self) -> str:
        return str(self.spec["date_column"])

    @property
    def actual_column(self) -> str:
        return str(self.spec["actual_column"])

    @property
    def history_table(self) -> str:
        return str(self.spec["history_table"])

    @property
    def moving_average_window(self) -> int:
        return int(self.spec.get("moving_average_window", 7))

    @property
    def max_entities(self) -> int | None:
        value = self.spec.get("max_entities")
        return int(value) if value is not None else None

    @property
    def baselines(self) -> list[str]:
        return list(self.spec["baselines"])

    @property
    def primary_metric(self) -> str:
        return str(self.spec["metric_policy"]["primary_metric"])

    @property
    def target(self) -> str:
        return self.forecast_contract.target

    @property
    def grain(self) -> str:
        dimensions = [
            dimension.removesuffix("_id") for dimension in self.forecast_contract.dimensions
        ]
        return "-".join([*dimensions, self.forecast_contract.frequency])

    @property
    def metric_policy(self) -> dict[str, Any]:
        return {
            "evaluation_protocol": "rolling_origin",
            **cast(dict[str, Any], self.spec["metric_policy"]),
        }

    def origin_plan_rows(self) -> list[dict[str, Any]]:
        """Return serializable origin/horizon rows for dry-run planning and tests."""
        rows: list[dict[str, Any]] = []
        for origin in self.origins:
            for horizon in self.horizons:
                rows.append(
                    {
                        "backtest_contract_name": self.name,
                        "forecast_contract_name": self.forecast_contract.name,
                        "model_config_name": self.model_config_name,
                        "origin_date": origin.isoformat(),
                        "horizon": horizon,
                        "train_window_days": self.train_window_days,
                    }
                )
        return rows


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Backtest contract not found: {path}")
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping at root of {path}")
    return data


def _require_list(spec: dict[str, Any], field: str) -> list[Any]:
    value = spec.get(field)
    if not isinstance(value, list) or not value:
        raise ValueError(f"backtest.{field} must be a non-empty list")
    return value


def _resolve_origins(spec: dict[str, Any]) -> tuple[date, ...]:
    explicit_origins = spec.get("origins")
    origin_policy = spec.get("origin_policy")
    if explicit_origins and origin_policy:
        raise ValueError("backtest must define either origins or origin_policy, not both")
    if explicit_origins:
        if not isinstance(explicit_origins, list) or not explicit_origins:
            raise ValueError("backtest.origins must be a non-empty list")
        return tuple(parse_backfill_date(item) for item in explicit_origins)
    if not isinstance(origin_policy, dict):
        raise ValueError("backtest.origin_policy is required when origins are not provided")

    start_value = origin_policy.get("start_date")
    end_value = origin_policy.get("end_date")
    if not isinstance(start_value, (str, date)) or not isinstance(end_value, (str, date)):
        raise ValueError("backtest.origin_policy start_date and end_date are required")
    start = parse_backfill_date(start_value)
    end = parse_backfill_date(end_value)
    interval_days = int(origin_policy.get("interval_days", 1))
    origins = tuple(iter_backfill_dates(start, end, interval_days=interval_days))
    if not origins:
        raise ValueError("backtest.origin_policy produced no origins")
    return origins


def validate_backtest_contract(raw: dict[str, Any]) -> BacktestContract:
    """Validate and normalize a backtest contract mapping."""
    spec = raw.get("backtest")
    if not isinstance(spec, dict):
        raise ValueError("backtest contract must contain a backtest mapping")

    required_scalars = [
        "name",
        "forecast_contract_path",
        "model_config_name",
        "train_window_days",
    ]
    for field in required_scalars:
        if spec.get(field) in (None, ""):
            raise ValueError(f"backtest.{field} is required")

    forecast_contract = load_forecast_contract(spec["forecast_contract_path"])
    model_config = load_model_config(str(spec["model_config_name"]))

    origins = _resolve_origins(spec)
    spec["origins"] = [origin.isoformat() for origin in origins]

    horizons = _require_list(spec, "horizons")
    if not all(isinstance(item, int) and item > 0 for item in horizons):
        raise ValueError("backtest.horizons must contain positive integers")
    normalized_horizons = sorted(set(horizons))
    contract_horizons = set(forecast_contract.horizons)
    unsupported = sorted(set(normalized_horizons).difference(contract_horizons))
    if unsupported:
        raise ValueError(
            "backtest.horizons must be a subset of forecast contract horizons; "
            f"unsupported: {unsupported}"
        )
    spec["horizons"] = normalized_horizons

    model_horizons = (model_config.get("inputs") or {}).get("prediction_horizons")
    if not isinstance(model_horizons, list) or not model_horizons:
        raise ValueError(
            f"Model config {spec['model_config_name']!r} must declare " "inputs.prediction_horizons"
        )
    normalized_model_horizons = sorted(set(model_horizons))
    if normalized_horizons != normalized_model_horizons:
        raise ValueError(
            "backtest.horizons must exactly match the model config "
            f"prediction_horizons; backtest={normalized_horizons}, "
            f"model={normalized_model_horizons}"
        )

    if int(spec["train_window_days"]) <= 0:
        raise ValueError("backtest.train_window_days must be positive")

    segment_columns = spec.get("segment_columns") or []
    if not isinstance(segment_columns, list):
        raise ValueError("backtest.segment_columns must be a list")
    if not all(isinstance(item, str) and item for item in segment_columns):
        raise ValueError("backtest.segment_columns must contain non-empty strings")
    spec["segment_columns"] = segment_columns

    for field in ("entity_columns",):
        values = _require_list(spec, field)
        if not all(isinstance(item, str) and item for item in values):
            raise ValueError(f"backtest.{field} must contain non-empty strings")
    for field in ("date_column", "actual_column", "history_table"):
        if not isinstance(spec.get(field), str) or not spec[field]:
            raise ValueError(f"backtest.{field} must be a non-empty string")
    validate_bq_table_id(str(spec["history_table"]))
    if int(spec.get("moving_average_window", 7)) < 1:
        raise ValueError("backtest.moving_average_window must be positive")

    max_entities = spec.get("max_entities")
    if max_entities is not None and int(max_entities) < 1:
        raise ValueError("backtest.max_entities must be positive when provided")

    baselines = _require_list(spec, "baselines")
    invalid_baselines = sorted(set(baselines).difference(ALLOWED_BASELINES))
    if invalid_baselines:
        raise ValueError(f"Unsupported backtest baselines: {invalid_baselines}")
    spec["baselines"] = sorted(set(baselines))

    metric_policy = spec.get("metric_policy")
    if not isinstance(metric_policy, dict):
        raise ValueError("backtest.metric_policy is required")
    primary_metric = metric_policy.get("primary_metric")
    if primary_metric not in ALLOWED_METRICS:
        raise ValueError(
            f"backtest.metric_policy.primary_metric must be one of {sorted(ALLOWED_METRICS)}"
        )
    metric_policy["lower_is_better"] = bool(metric_policy.get("lower_is_better", True))
    selection_scope = metric_policy.get("selection_scope") or []
    if not isinstance(selection_scope, list) or not selection_scope:
        raise ValueError("backtest.metric_policy.selection_scope must be a non-empty list")

    gates = spec.get("promotion_gates") or {}
    if not isinstance(gates, dict):
        raise ValueError("backtest.promotion_gates must be a mapping")
    for field in (
        "min_baseline_improvement_pct",
        "max_bias_abs_pct",
        "min_prediction_completeness",
    ):
        if field in gates and float(gates[field]) < 0:
            raise ValueError(f"backtest.promotion_gates.{field} must be >= 0")

    return BacktestContract(
        raw={"backtest": spec},
        forecast_contract=forecast_contract,
        origins=origins,
    )


def load_backtest_contract(path: str | Path | None = None) -> BacktestContract:
    """Load and validate a backtest contract YAML file."""
    contract_path = Path(path) if path else DEFAULT_BACKTEST_CONTRACT_PATH
    return validate_backtest_contract(_load_yaml(contract_path))
