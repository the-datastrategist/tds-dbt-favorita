"""Deterministic routing, calibration, reconciliation, and draft validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from vertex.config.forecast_contract import ForecastContract
from vertex.config.hierarchy import HierarchyConfig
from vertex.evaluation.calibration import fit_horizon_calibrator
from vertex.evaluation.reconciliation import coherence_violations, reconcile_forecasts
from vertex.utils.data_utils import get_hash
from vertex.utils.forecast_outputs import build_forecast_output_rows
from vertex.utils.forecast_publication import validate_publication_batch


@dataclass(frozen=True)
class ForecastRunPins:
    """Material inputs frozen for one logical publication run."""

    champion_candidate_id: str
    model_run_id: str
    feature_version: str
    feature_availability_hash: str
    data_cutoff: Any
    source_cutoff_json: dict[str, Any]
    eligibility_snapshot_id: str
    code_sha: str


@dataclass(frozen=True)
class ForecastPipelineResult:
    """Validated draft rows and immutable stage/gate evidence."""

    forecast_run_id: str
    rows: pd.DataFrame
    stage_records: list[dict[str, Any]]
    validation_checks: list[dict[str, Any]]


def build_forecast_run_id(
    contract: ForecastContract,
    *,
    forecast_origin: Any,
    pins: ForecastRunPins,
) -> str:
    """Return the retry-stable ID for all material run inputs."""
    return get_hash(
        {
            "forecast_contract_hash": contract.hash,
            "forecast_origin": str(pd.Timestamp(forecast_origin)),
            "champion_candidate_id": pins.champion_candidate_id,
            "model_run_id": pins.model_run_id,
            "feature_version": pins.feature_version,
            "feature_availability_hash": pins.feature_availability_hash,
            "data_cutoff": str(pd.Timestamp(pins.data_cutoff)),
            "data_cutoff_set": pins.source_cutoff_json,
            "eligibility_snapshot_id": pins.eligibility_snapshot_id,
            "code_sha": pins.code_sha,
        }
    )


def eligibility_snapshot_id(
    prediction_rows: pd.DataFrame,
    contract: ForecastContract,
) -> str:
    """Fingerprint the frozen entity, target-date, and horizon population."""
    required = {*contract.dimensions, "date", "forecast_horizon"}
    if missing := sorted(required.difference(prediction_rows.columns)):
        raise ValueError(f"prediction rows cannot form eligibility snapshot: {missing}")
    work = prediction_rows.copy()
    origin = pd.to_datetime(work["date"], errors="raise")
    target = origin + pd.to_timedelta(work["forecast_horizon"].astype(int), unit="D")
    keys = []
    for index, row in work.iterrows():
        entity = {
            dimension: row[dimension].item() if hasattr(row[dimension], "item") else row[dimension]
            for dimension in contract.dimensions
        }
        keys.append(
            {
                "entity": entity,
                "target_date": str(target.loc[index].date()),
                "horizon": int(row["forecast_horizon"]),
            }
        )
    ordered = sorted(keys, key=lambda value: json.dumps(value, sort_keys=True))
    return get_hash(json.dumps(ordered, sort_keys=True, separators=(",", ":")))


def _stage_record(
    *,
    forecast_run_id: str,
    stage_name: str,
    stage_position: int,
    input_fingerprint: str,
    output: pd.DataFrame,
    component_run_id: str,
    completed_at: datetime,
) -> dict[str, Any]:
    identity = {"forecast_run_id": forecast_run_id, "stage_name": stage_name}
    return {
        "stage_run_id": get_hash(identity),
        **identity,
        "stage_position": stage_position,
        "component_run_id": component_run_id,
        "input_fingerprint": input_fingerprint,
        "output_fingerprint": get_hash(
            output.to_json(orient="records", date_format="iso", date_unit="us")
        ),
        "stage_status": "completed",
        "input_row_count": len(output),
        "output_row_count": len(output),
        "started_at": completed_at,
        "finished_at": completed_at,
        "error_message": None,
    }


def _check(
    forecast_run_id: str,
    name: str,
    passed: bool,
    *,
    observed: float | None = None,
    threshold: float | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    identity = {"forecast_run_id": forecast_run_id, "check_name": name}
    return {
        "validation_check_id": get_hash(identity),
        **identity,
        "severity": "blocking",
        "passed": passed,
        "observed_value": observed,
        "threshold_value": threshold,
        "details_json": details or {},
        "checked_at": datetime.now(timezone.utc),
    }


def _attach_strategy(
    rows: pd.DataFrame,
    calibration_rows: pd.DataFrame,
    contract: ForecastContract,
) -> pd.DataFrame:
    """Route sparse series to the configured global champion using OOS history."""
    result = rows.copy()
    if "entity_key_json" not in calibration_rows or "actual" not in calibration_rows:
        raise ValueError("routing requires entity-keyed out-of-sample actual history")
    profiles: dict[str, tuple[str | None, str]] = {}
    for entity_key, group in calibration_rows.groupby("entity_key_json", dropna=False):
        demand = pd.to_numeric(group["actual"], errors="coerce").dropna()
        nonzero_count = int((demand > 0).sum())
        history_length = len(demand)
        average_interval = history_length / nonzero_count if nonzero_count else None
        cold_start = history_length < 28 or nonzero_count < 3
        intermittent = nonzero_count == 0 or (
            average_interval is not None and average_interval >= 1.32
        )
        reason = "cold_start" if cold_start else "intermittent_demand" if intermittent else None
        profiles[str(entity_key)] = (reason, "medium" if reason else "high")

    entity_keys = []
    for _, row in result.iterrows():
        payload = {
            dimension: row[dimension].item() if hasattr(row[dimension], "item") else row[dimension]
            for dimension in contract.dimensions
        }
        entity_keys.append(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    decisions = [profiles.get(key, ("no_routing_history", "medium")) for key in entity_keys]
    result["forecast_strategy"] = "global_model"
    result["fallback_reason"] = [decision[0] for decision in decisions]
    result["confidence_flag"] = [decision[1] for decision in decisions]
    if result[["forecast_strategy", "confidence_flag"]].isna().any(axis=None):
        raise ValueError("routing must produce strategy and confidence metadata for every row")
    return result


def execute_forecast_pipeline(
    prediction_rows: pd.DataFrame,
    calibration_rows: pd.DataFrame,
    *,
    contract: ForecastContract,
    pins: ForecastRunPins,
    hierarchy_config: HierarchyConfig | None = None,
    hierarchy_nodes: pd.DataFrame | None = None,
    hierarchy_edges: pd.DataFrame | None = None,
    minimum_calibration_residuals: int = 20,
    completed_at: datetime | None = None,
) -> ForecastPipelineResult:
    """Execute ordered numerical stages and return a validated atomic draft."""
    if prediction_rows.empty:
        raise ValueError("prediction rows cannot be empty")
    origins = pd.to_datetime(prediction_rows["date"], errors="raise")
    if origins.nunique() != 1:
        raise ValueError("one publication run must contain exactly one forecast origin")
    eligibility_id = eligibility_snapshot_id(prediction_rows, contract)
    if eligibility_id != pins.eligibility_snapshot_id:
        raise ValueError("prediction rows do not match the pinned eligibility snapshot")
    forecast_run_id = build_forecast_run_id(
        contract,
        forecast_origin=origins.iloc[0],
        pins=pins,
    )
    now = completed_at or datetime.now(timezone.utc)
    score_fingerprint = get_hash(
        prediction_rows.to_json(orient="records", date_format="iso", date_unit="us")
    )
    stages: list[dict[str, Any]] = [
        _stage_record(
            forecast_run_id=forecast_run_id,
            stage_name="score",
            stage_position=1,
            input_fingerprint=get_hash(
                {
                    "champion_candidate_id": pins.champion_candidate_id,
                    "model_run_id": pins.model_run_id,
                    "eligibility_snapshot_id": pins.eligibility_snapshot_id,
                }
            ),
            output=prediction_rows,
            component_run_id=pins.model_run_id,
            completed_at=now,
        )
    ]

    routed = _attach_strategy(prediction_rows, calibration_rows, contract)
    routed["predict_run_id"] = forecast_run_id
    stages.append(
        _stage_record(
            forecast_run_id=forecast_run_id,
            stage_name="route",
            stage_position=2,
            input_fingerprint=score_fingerprint,
            output=routed,
            component_run_id=get_hash({"forecast_run_id": forecast_run_id, "stage": "route"}),
            completed_at=now,
        )
    )

    calibrator = fit_horizon_calibrator(
        calibration_rows,
        minimum_residuals=minimum_calibration_residuals,
    )
    calibrated = calibrator.transform(
        routed,
        quantiles=contract.quantiles,
        horizon_column="forecast_horizon",
    )
    calibration_run_id = get_hash(
        {
            "forecast_run_id": forecast_run_id,
            "residuals_by_horizon": calibrator.residuals_by_horizon,
            "quantiles": contract.quantiles,
        }
    )
    calibrated["calibration_method"] = "symmetric_split_conformal"
    calibrated["calibration_run_id"] = calibration_run_id
    stages.append(
        _stage_record(
            forecast_run_id=forecast_run_id,
            stage_name="calibrate",
            stage_position=3,
            input_fingerprint=stages[-1]["output_fingerprint"],
            output=calibrated,
            component_run_id=calibration_run_id,
            completed_at=now,
        )
    )

    if contract.reconciliation_policy == "none":
        reconciled = calibrated.copy()
        reconciled["hierarchy_version"] = None
        reconciled["reconciliation_method"] = "none"
        reconciled["reconciliation_run_id"] = None
        reconciliation_run_id = get_hash(
            {"forecast_run_id": forecast_run_id, "reconciliation_method": "none"}
        )
    else:
        if hierarchy_config is None or hierarchy_nodes is None or hierarchy_edges is None:
            raise ValueError("hierarchical publication requires config, nodes, and edges")
        if hierarchy_config.method != contract.reconciliation_policy:
            raise ValueError("hierarchy method does not match forecast contract")
        reconciliation_run_id = get_hash(
            {"forecast_run_id": forecast_run_id, "hierarchy_hash": hierarchy_config.hash}
        )
        reconciled = reconcile_forecasts(
            calibrated,
            hierarchy_nodes,
            hierarchy_edges,
            method=hierarchy_config.method,
            group_columns=("date", "forecast_date", "forecast_horizon"),
            middle_level=hierarchy_config.middle_level,
        )
        for quantile_column in ("prediction_p10", "prediction_p50", "prediction_p90"):
            violations = coherence_violations(
                reconciled,
                hierarchy_nodes,
                hierarchy_edges,
                value_column=quantile_column,
                group_columns=("date", "forecast_date", "forecast_horizon"),
                tolerance_abs=hierarchy_config.tolerance_abs,
            )
            if not violations.empty:
                raise ValueError(f"reconciliation coherence failed for {quantile_column}")
        reconciled["prediction_lower"] = reconciled["prediction_p10"]
        reconciled["prediction"] = reconciled["prediction_p50"]
        reconciled["prediction_upper"] = reconciled["prediction_p90"]
        reconciled["hierarchy_version"] = hierarchy_config.version
        reconciled["reconciliation_run_id"] = reconciliation_run_id
    stages.append(
        _stage_record(
            forecast_run_id=forecast_run_id,
            stage_name="reconcile",
            stage_position=4,
            input_fingerprint=stages[-1]["output_fingerprint"],
            output=reconciled,
            component_run_id=reconciliation_run_id,
            completed_at=now,
        )
    )

    canonical = build_forecast_output_rows(
        reconciled,
        contract=contract,
        feature_version=pins.feature_version,
        code_sha=pins.code_sha,
        data_cutoff=pins.data_cutoff,
        forecast_status="draft",
    )
    validate_publication_batch(canonical, contract)
    expected = len(prediction_rows)
    checks = [
        _check(
            forecast_run_id,
            "prediction_completeness",
            len(canonical) == expected,
            observed=len(canonical) / expected,
            threshold=1.0,
        ),
        _check(
            forecast_run_id,
            "quantile_ordering",
            bool(
                (
                    (canonical["prediction_p10"] <= canonical["prediction_p50"])
                    & (canonical["prediction_p50"] <= canonical["prediction_p90"])
                ).all()
            ),
        ),
        _check(
            forecast_run_id,
            "point_in_time_cutoff",
            pd.Timestamp(pins.data_cutoff) <= origins.iloc[0],
            details={"data_cutoff": str(pins.data_cutoff), "forecast_origin": str(origins.iloc[0])},
        ),
    ]
    failed = [check["check_name"] for check in checks if not check["passed"]]
    if failed:
        raise ValueError(f"blocking publication gates failed: {', '.join(failed)}")
    stages.append(
        _stage_record(
            forecast_run_id=forecast_run_id,
            stage_name="validate",
            stage_position=5,
            input_fingerprint=stages[-1]["output_fingerprint"],
            output=canonical,
            component_run_id=get_hash({"forecast_run_id": forecast_run_id, "stage": "validate"}),
            completed_at=now,
        )
    )
    return ForecastPipelineResult(forecast_run_id, canonical, stages, checks)
