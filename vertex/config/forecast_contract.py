"""Forecast contract loader and validation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml

from vertex.utils.data_utils import get_hash

DEFAULT_FORECAST_CONTRACT_PATH = Path(__file__).resolve().parent / "forecast_contract.yaml"

VALID_FREQUENCIES = frozenset({"day"})
VALID_RECONCILIATION_POLICIES = frozenset({"none", "bottom_up", "top_down", "middle_out", "mint"})
VALID_DEMAND_POLICIES = frozenset(
    {
        "observed_sales_only",
        "exclude_stockout_days",
        "impute_lost_demand_simple",
        "external_unconstrained_demand",
    }
)
VALID_FORECAST_STRATEGIES = frozenset(
    {
        "entity_model",
        "global_model",
        "aggregate_allocation",
        "intermittent_rate_baseline",
        "seasonal_baseline",
        "business_default",
    }
)
VALID_CALIBRATION_METHODS = frozenset({"symmetric_split_conformal"})


@dataclass(frozen=True)
class ForecastContract:
    """Validated forecast contract with stable hash semantics."""

    raw: dict[str, Any]

    @property
    def spec(self) -> dict[str, Any]:
        return cast(dict[str, Any], self.raw["forecast"])

    @property
    def name(self) -> str:
        return str(self.spec["name"])

    @property
    def hash(self) -> str:
        return get_hash(self.raw)

    @property
    def dimensions(self) -> list[str]:
        return list(self.spec["dimensions"])

    @property
    def horizons(self) -> list[int]:
        return list(self.spec["horizons"])

    @property
    def quantiles(self) -> list[float]:
        return list(self.spec["quantiles"])

    @property
    def target(self) -> str:
        return str(self.spec["target"])

    @property
    def target_unit(self) -> str:
        return str(self.spec["target_unit"])

    @property
    def frequency(self) -> str:
        return str(self.spec["frequency"])

    @property
    def timezone(self) -> str:
        return str(self.spec["timezone"])

    @property
    def issue_schedule(self) -> str:
        return str(self.spec["issue_schedule"])

    @property
    def training_window_days(self) -> int:
        return int(self.spec["training_window_days"])

    @property
    def reconciliation_policy(self) -> str:
        return str(self.spec["reconciliation_policy"])

    @property
    def demand_policy(self) -> str:
        return str(self.spec["demand_policy"])

    @property
    def routing(self) -> dict[str, Any]:
        return cast(dict[str, Any], self.spec["routing"])

    @property
    def calibration(self) -> dict[str, Any]:
        return cast(dict[str, Any], self.spec["calibration"])


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Forecast contract not found: {path}")
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping at root of {path}")
    return data


def _require_list(spec: dict[str, Any], field: str) -> list[Any]:
    value = spec.get(field)
    if not isinstance(value, list) or not value:
        raise ValueError(f"forecast.{field} must be a non-empty list")
    return value


def validate_forecast_contract(raw: dict[str, Any]) -> ForecastContract:
    """Validate and normalize a forecast contract mapping."""
    spec = raw.get("forecast")
    if not isinstance(spec, dict):
        raise ValueError("forecast contract must contain a forecast mapping")

    required_scalars = [
        "name",
        "target",
        "target_unit",
        "frequency",
        "timezone",
        "issue_schedule",
        "training_window_days",
        "reconciliation_policy",
        "demand_policy",
    ]
    for field in required_scalars:
        if spec.get(field) in (None, ""):
            raise ValueError(f"forecast.{field} is required")

    dimensions = _require_list(spec, "dimensions")
    if not all(isinstance(item, str) and item for item in dimensions):
        raise ValueError("forecast.dimensions must contain non-empty strings")

    horizons = _require_list(spec, "horizons")
    if not all(isinstance(item, int) and item > 0 for item in horizons):
        raise ValueError("forecast.horizons must contain positive integers")
    spec["horizons"] = sorted(set(horizons))

    quantiles = _require_list(spec, "quantiles")
    if not all(isinstance(item, (int, float)) and 0 < float(item) < 1 for item in quantiles):
        raise ValueError("forecast.quantiles must be between 0 and 1")
    spec["quantiles"] = sorted({float(item) for item in quantiles})

    known_future = set(_require_list(spec, "known_future_features"))
    observed = set(_require_list(spec, "observed_features"))
    overlap = known_future.intersection(observed)
    if overlap:
        raise ValueError(
            "features cannot be both known-future and observed: " f"{', '.join(sorted(overlap))}"
        )

    if spec["frequency"] not in VALID_FREQUENCIES:
        raise ValueError(f"forecast.frequency must be one of {sorted(VALID_FREQUENCIES)}")
    if spec["reconciliation_policy"] not in VALID_RECONCILIATION_POLICIES:
        raise ValueError(
            "forecast.reconciliation_policy must be one of "
            f"{sorted(VALID_RECONCILIATION_POLICIES)}"
        )
    if spec["demand_policy"] not in VALID_DEMAND_POLICIES:
        raise ValueError(f"forecast.demand_policy must be one of {sorted(VALID_DEMAND_POLICIES)}")
    if int(spec["training_window_days"]) <= 0:
        raise ValueError("forecast.training_window_days must be positive")

    hierarchy = spec.get("hierarchy") or []
    if spec["reconciliation_policy"] != "none" and not hierarchy:
        raise ValueError("forecast.hierarchy is required when reconciliation_policy != none")
    if hierarchy and not all(isinstance(item, str) and item for item in hierarchy):
        raise ValueError("forecast.hierarchy must contain non-empty strings")

    routing = spec.setdefault(
        "routing",
        {
            "allowed_strategies": sorted(VALID_FORECAST_STRATEGIES),
            "fallback_order": {
                "cold_start": ["global_model", "business_default"],
                "intermittent": ["intermittent_rate_baseline", "global_model", "business_default"],
            },
            "business_default": 0.0,
            "minimum_history": 28,
            "minimum_nonzero_observations": 3,
            "intermittent_adi_threshold": 1.32,
        },
    )
    if not isinstance(routing, dict):
        raise ValueError("forecast.routing must be a mapping")
    allowed = routing.get("allowed_strategies")
    if not isinstance(allowed, list) or not allowed:
        raise ValueError("forecast.routing.allowed_strategies must be a non-empty list")
    unknown = sorted(set(allowed).difference(VALID_FORECAST_STRATEGIES))
    if unknown:
        raise ValueError(f"forecast.routing contains unsupported strategies: {unknown}")
    fallback_order = routing.get("fallback_order")
    if not isinstance(fallback_order, dict):
        raise ValueError("forecast.routing.fallback_order must be a mapping")
    for classification in ("cold_start", "intermittent"):
        order = fallback_order.get(classification)
        if not isinstance(order, list) or not order:
            raise ValueError(
                f"forecast.routing.fallback_order.{classification} must be a non-empty list"
            )
        if not set(order).issubset(set(allowed)):
            raise ValueError(
                f"forecast.routing.fallback_order.{classification} must use allowed strategies"
            )
    for field in ("minimum_history", "minimum_nonzero_observations"):
        if int(routing.get(field, 0)) < 1:
            raise ValueError(f"forecast.routing.{field} must be positive")
    if float(routing.get("intermittent_adi_threshold", 0)) <= 0:
        raise ValueError("forecast.routing.intermittent_adi_threshold must be positive")

    calibration = spec.setdefault(
        "calibration",
        {
            "method": "symmetric_split_conformal",
            "lookback_origins": 12,
            "minimum_residuals": 20,
        },
    )
    if not isinstance(calibration, dict):
        raise ValueError("forecast.calibration must be a mapping")
    if calibration.get("method") not in VALID_CALIBRATION_METHODS:
        raise ValueError(
            f"forecast.calibration.method must be one of {sorted(VALID_CALIBRATION_METHODS)}"
        )
    for field in ("lookback_origins", "minimum_residuals"):
        if int(calibration.get(field, 0)) < 1:
            raise ValueError(f"forecast.calibration.{field} must be positive")

    return ForecastContract(raw={"forecast": spec})


def load_forecast_contract(path: str | Path | None = None) -> ForecastContract:
    """Load and validate a forecast contract YAML file."""
    contract_path = Path(path) if path else DEFAULT_FORECAST_CONTRACT_PATH
    return validate_forecast_contract(_load_yaml(contract_path))
