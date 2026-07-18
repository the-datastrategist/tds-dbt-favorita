"""Series classification and deterministic forecast strategy routing."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Sequence

import pandas as pd

from vertex.utils.data_utils import get_hash


@dataclass(frozen=True)
class RoutingPolicy:
    minimum_history: int = 28
    minimum_nonzero_observations: int = 3
    intermittent_adi_threshold: float = 1.32


@dataclass(frozen=True)
class StrategyAvailability:
    entity_model: bool = True
    global_model: bool = True
    aggregate_allocation: bool = True
    seasonal_or_rate_baseline: bool = True
    business_default: bool = True


@dataclass(frozen=True)
class StrategyDecision:
    forecast_strategy: str
    fallback_reason: str | None
    confidence_flag: str


def _entity_key(values: tuple[object, ...], columns: Sequence[str]) -> str:
    payload = {
        column: value.item() if hasattr(value, "item") else value
        for column, value in zip(columns, values)
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def classify_series(
    observations: pd.DataFrame,
    *,
    entity_columns: Sequence[str],
    demand_column: str,
    policy: RoutingPolicy = RoutingPolicy(),
) -> pd.DataFrame:
    """Return one deterministic classification row per entity."""
    required = set(entity_columns) | {demand_column}
    missing = sorted(required - set(observations.columns))
    if missing:
        raise ValueError(f"observations are missing required columns: {missing}")
    if observations.empty:
        return pd.DataFrame(
            columns=[
                "entity_key_json",
                "history_length",
                "nonzero_observation_count",
                "average_demand_interval",
                "coefficient_of_variation_squared",
                "is_intermittent",
                "is_cold_start",
                "recommended_strategy",
                "classification_run_id",
            ]
        )

    rows: list[dict[str, object]] = []
    grouper = entity_columns[0] if len(entity_columns) == 1 else list(entity_columns)
    for raw_key, group in observations.groupby(grouper, dropna=False, sort=True):
        key = raw_key if isinstance(raw_key, tuple) else (raw_key,)
        demand = pd.to_numeric(group[demand_column], errors="coerce").fillna(0.0)
        history_length = len(demand)
        nonzero = demand[demand > 0]
        nonzero_count = len(nonzero)
        adi = float(history_length / nonzero_count) if nonzero_count else None
        mean_nonzero = float(nonzero.mean()) if nonzero_count else 0.0
        cv_squared = (
            float(nonzero.var(ddof=0) / (mean_nonzero**2))
            if nonzero_count and mean_nonzero
            else 0.0
        )
        cold_start = (
            history_length < policy.minimum_history
            or nonzero_count < policy.minimum_nonzero_observations
        )
        intermittent = nonzero_count == 0 or (
            adi is not None and adi >= policy.intermittent_adi_threshold
        )
        recommended = (
            "global_model"
            if cold_start
            else "intermittent_rate_baseline" if intermittent else "entity_model"
        )
        entity_key_json = _entity_key(key, entity_columns)
        row = {
            "entity_key_json": entity_key_json,
            "history_length": history_length,
            "nonzero_observation_count": nonzero_count,
            "average_demand_interval": adi,
            "coefficient_of_variation_squared": cv_squared,
            "is_intermittent": intermittent,
            "is_cold_start": cold_start,
            "recommended_strategy": recommended,
        }
        row["classification_run_id"] = get_hash({"profile": row, "policy": policy.__dict__})
        rows.append(row)
    return pd.DataFrame(rows)


def choose_forecast_strategy(
    *,
    is_cold_start: bool,
    is_intermittent: bool,
    availability: StrategyAvailability = StrategyAvailability(),
) -> StrategyDecision:
    """Apply the ordered fallback contract and return non-null provenance."""
    reason = "cold_start" if is_cold_start else "intermittent_demand" if is_intermittent else None
    if availability.entity_model and not is_cold_start and not is_intermittent:
        return StrategyDecision("entity_model", None, "high")
    if availability.global_model:
        return StrategyDecision("global_model", reason or "entity_model_unavailable", "medium")
    if availability.aggregate_allocation:
        return StrategyDecision("aggregate_allocation", reason or "model_unavailable", "medium")
    if availability.seasonal_or_rate_baseline:
        strategy = "intermittent_rate_baseline" if is_intermittent else "seasonal_baseline"
        return StrategyDecision(strategy, reason or "model_unavailable", "low")
    if availability.business_default:
        return StrategyDecision("business_default", reason or "no_forecast_method_available", "low")
    raise ValueError("routing policy has no available forecast strategy")


def attach_strategy_metadata(
    prediction_rows: pd.DataFrame,
    *,
    decision: StrategyDecision,
) -> pd.DataFrame:
    """Attach routing provenance before canonical forecast persistence."""
    result = prediction_rows.copy()
    result["forecast_strategy"] = decision.forecast_strategy
    result["fallback_reason"] = decision.fallback_reason
    result["confidence_flag"] = decision.confidence_flag
    return result
