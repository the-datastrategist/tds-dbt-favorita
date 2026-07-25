"""Canonical forecast output row schema and builders."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd

from vertex.config.feature_availability import feature_cutoff_metadata_from_frame
from vertex.config.forecast_contract import ForecastContract, load_forecast_contract
from vertex.utils.bigquery_utils import insert_rows_idempotent, merge_row_to_bigquery
from vertex.utils.data_utils import get_hash
from vertex.utils.forecast_lifecycle import build_status_events, validate_forecast_status
from vertex.utils.run_context import get_git_sha

FORECAST_OUTPUT_COLUMNS = [
    "forecast_output_id",
    "source_prediction_id",
    "forecast_run_id",
    "forecast_contract_name",
    "forecast_contract_hash",
    "contract_enforced",
    "forecast_origin",
    "target_date",
    "horizon",
    "grain",
    "entity_key_json",
    "target",
    "target_unit",
    "prediction_p10",
    "prediction_p50",
    "prediction_p90",
    "forecast_strategy",
    "fallback_reason",
    "confidence_flag",
    "calibration_method",
    "calibration_run_id",
    "hierarchy_version",
    "reconciliation_method",
    "reconciliation_run_id",
    "statistical_forecast",
    "planner_override",
    "approved_forecast",
    "published_forecast",
    "forecast_status",
    "model_run_id",
    "model_id",
    "config_name",
    "model_family",
    "model_type",
    "feature_version",
    "code_sha",
    "data_cutoff",
    "model_artifact_uri",
    "created_at",
]


def _json_safe_entity(row: pd.Series, dimensions: list[str]) -> str:
    payload: dict[str, Any] = {}
    for dimension in dimensions:
        value = row.get(dimension)
        if pd.isna(value):
            value = None
        elif hasattr(value, "item"):
            value = value.item()
        payload[dimension] = value
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def build_forecast_output_rows(
    prediction_rows: pd.DataFrame,
    *,
    contract: ForecastContract,
    feature_version: Optional[str] = None,
    code_sha: Optional[str] = None,
    data_cutoff: Optional[Any] = None,
    forecast_status: str = "draft",
) -> pd.DataFrame:
    """Map standard model prediction rows into canonical forecast output rows."""
    if prediction_rows.empty:
        return pd.DataFrame(columns=FORECAST_OUTPUT_COLUMNS)

    work = prediction_rows.copy()
    validate_forecast_status(forecast_status)
    horizon = work.get("forecast_horizon")
    if horizon is None:
        horizon = pd.Series([None] * len(work), index=work.index, dtype=object)
    else:
        horizon = horizon.where(horizon.notna(), None).astype(object)

    invalid_horizons = sorted(
        {int(value) for value in horizon.dropna().tolist()} - set(contract.horizons)
    )
    if invalid_horizons:
        raise ValueError(
            f"prediction horizons {invalid_horizons} are not in contract horizons "
            f"{contract.horizons}"
        )
    if horizon.isna().any():
        raise ValueError("every canonical forecast row must include a horizon")

    source_date = pd.to_datetime(work["date"], errors="coerce")
    if "forecast_date" in work.columns:
        explicit_target = pd.to_datetime(work["forecast_date"], errors="coerce")
    else:
        explicit_target = pd.Series(pd.NaT, index=work.index)
    calculated_target = source_date + pd.to_timedelta(horizon.astype(int), unit="D")
    target_date = explicit_target.where(explicit_target.notna(), calculated_target)
    forecast_origin = target_date - pd.to_timedelta(horizon.astype(int), unit="D")
    if target_date.isna().any() or forecast_origin.isna().any():
        raise ValueError("every canonical forecast row must have a valid origin and target date")

    required_provenance = {
        "feature_version": feature_version,
        "code_sha": code_sha,
        "data_cutoff": data_cutoff,
    }
    missing = [name for name, value in required_provenance.items() if value in (None, "")]
    for column in ("model_id", "config_name", "model_type", "model_artifact_uri"):
        if column not in work.columns or work[column].isna().any() or (work[column] == "").any():
            missing.append(column)
    if missing:
        raise ValueError(f"canonical forecast provenance is incomplete: {', '.join(missing)}")

    dimensions = [col for col in contract.dimensions if col in work.columns]
    missing_dimensions = sorted(set(contract.dimensions) - set(dimensions))
    if missing_dimensions:
        raise ValueError(f"prediction rows are missing contract dimensions: {missing_dimensions}")
    if work[dimensions].isna().any(axis=None):
        raise ValueError("contract dimension values cannot be null")

    entity_keys = work.apply(lambda row: _json_safe_entity(row, dimensions), axis=1)
    forecast_run_ids = work["predict_run_id"]
    if forecast_run_ids.nunique(dropna=False) != 1 or forecast_run_ids.isna().any():
        raise ValueError("a canonical persistence batch must contain exactly one forecast_run_id")
    created_at = work["run_at"]
    forecast_strategy = work.get("forecast_strategy", pd.Series("entity_model", index=work.index))
    fallback_reason = work.get("fallback_reason", pd.Series(None, index=work.index, dtype=object))
    confidence_flag = work.get("confidence_flag", pd.Series("high", index=work.index))
    if forecast_strategy.isna().any() or (forecast_strategy == "").any():
        raise ValueError("every canonical forecast row must include a forecast_strategy")
    invalid_confidence = sorted(set(confidence_flag.dropna()) - {"high", "medium", "low"})
    if confidence_flag.isna().any() or invalid_confidence:
        raise ValueError("confidence_flag must be non-null and one of high, medium, or low")

    output_ids = [
        get_hash(
            {
                "forecast_run_id": run_id,
                "entity_key_json": entity_key,
                "target_date": str(target),
                "horizon": None if pd.isna(h) else int(h),
                "contract_hash": contract.hash,
            }
        )
        for run_id, entity_key, target, h in zip(
            forecast_run_ids, entity_keys, target_date, horizon
        )
    ]

    frame = pd.DataFrame(
        {
            "forecast_output_id": output_ids,
            "source_prediction_id": work["prediction_id"],
            "forecast_run_id": forecast_run_ids,
            "forecast_contract_name": contract.name,
            "forecast_contract_hash": contract.hash,
            "contract_enforced": True,
            "forecast_origin": forecast_origin,
            "target_date": target_date.dt.date,
            "horizon": horizon,
            "grain": ",".join(contract.dimensions),
            "entity_key_json": entity_keys,
            "target": contract.target,
            "target_unit": contract.target_unit,
            "prediction_p10": work.get("prediction_lower"),
            "prediction_p50": work["prediction"],
            "prediction_p90": work.get("prediction_upper"),
            "forecast_strategy": forecast_strategy,
            "fallback_reason": fallback_reason,
            "confidence_flag": confidence_flag,
            "calibration_method": work.get("calibration_method"),
            "calibration_run_id": work.get("calibration_run_id"),
            "hierarchy_version": work.get("hierarchy_version"),
            "reconciliation_method": work.get(
                "reconciliation_method", pd.Series("none", index=work.index)
            ),
            "reconciliation_run_id": work.get("reconciliation_run_id"),
            "statistical_forecast": work["prediction"],
            "planner_override": None,
            "approved_forecast": None,
            "published_forecast": None,
            "forecast_status": forecast_status,
            "model_run_id": work["model_run_id"],
            "model_id": work["model_id"],
            "config_name": work["config_name"],
            "model_family": work["model_family"],
            "model_type": work["model_type"],
            "feature_version": feature_version,
            "code_sha": code_sha,
            "data_cutoff": data_cutoff,
            "model_artifact_uri": work["model_artifact_uri"],
            "created_at": created_at,
        }
    )
    return frame[FORECAST_OUTPUT_COLUMNS]


def _feature_version(config: dict[str, Any]) -> str:
    inputs = config.get("inputs") or {}
    explicit = inputs.get("feature_version") or inputs.get("feature_table_version")
    if explicit:
        return str(explicit)
    return get_hash(
        {
            "train_sql_query": inputs.get("train_sql_query"),
            "predict_sql_query": inputs.get("predict_sql_query"),
            "id_columns": inputs.get("id_columns"),
            "excluded_columns": inputs.get("excluded_columns"),
            "categorical_columns": inputs.get("categorical_columns"),
        }
    )


def build_contract_registration_row(
    contract: ForecastContract, registered_at: datetime
) -> dict[str, Any]:
    """Build the immutable registry row for a forecast contract."""
    spec = contract.spec
    return {
        "forecast_contract_name": contract.name,
        "forecast_contract_hash": contract.hash,
        "registered_at": registered_at,
        "target": contract.target,
        "target_unit": contract.target_unit,
        "frequency": contract.frequency,
        "timezone": contract.timezone,
        "issue_schedule": contract.issue_schedule,
        "dimensions": contract.dimensions,
        "horizons": contract.horizons,
        "quantiles": contract.quantiles,
        "training_window_days": contract.training_window_days,
        "known_future_features": spec["known_future_features"],
        "observed_features": spec["observed_features"],
        "hierarchy": spec.get("hierarchy") or [],
        "reconciliation_policy": contract.reconciliation_policy,
        "demand_policy": contract.demand_policy,
        "contract_json": contract.raw,
        "is_active": True,
    }


def write_forecast_outputs_if_configured(
    *,
    config: dict[str, Any],
    prediction_rows: pd.DataFrame,
    project_id: Optional[str] = None,
    feature_cutoff_metadata: Optional[dict[str, Any]] = None,
) -> int:
    """
    Write canonical forecast output rows when outputs.forecast_output_table is configured.

    This keeps the canonical platform contract opt-in during migration from the existing
    model-oriented prediction table.
    """
    outputs = config.get("outputs") or {}
    forecast_output_table = outputs.get("forecast_output_table")
    if not forecast_output_table:
        return 0

    inputs = config.get("inputs") or {}
    contract_path = (
        outputs.get("forecast_contract_path")
        or config.get("forecast_contract_path")
        or inputs.get("forecast_contract_path")
    )
    contract = load_forecast_contract(contract_path)
    cutoff_metadata = feature_cutoff_metadata or feature_cutoff_metadata_from_frame(
        prediction_rows, date_column="date"
    )
    feature_version = _feature_version(config)
    code_sha = get_git_sha()
    if not code_sha:
        raise ValueError("code_sha is required to persist canonical forecast outputs")
    data_cutoff = (
        inputs.get("data_cutoff")
        or cutoff_metadata.get("data_cutoff")
        or prediction_rows["run_at"].max()
    )
    rows = build_forecast_output_rows(
        prediction_rows,
        contract=contract,
        feature_version=feature_version,
        code_sha=code_sha,
        data_cutoff=data_cutoff,
        forecast_status=outputs.get("forecast_status", "draft"),
    )
    if rows.empty:
        return 0
    now = datetime.now(timezone.utc)
    run_id = str(rows["forecast_run_id"].iloc[0])
    contract_table = outputs.get("forecast_contract_table")
    runs_table = outputs.get("forecast_runs_table")
    status_table = outputs.get("forecast_status_history_table")
    persistence_tables = (contract_table, runs_table, status_table)
    if not all(isinstance(table, str) and table.strip() for table in persistence_tables):
        raise ValueError(
            "canonical persistence requires forecast_contract_table, forecast_runs_table, "
            "and forecast_status_history_table"
        )
    assert isinstance(contract_table, str)
    assert isinstance(runs_table, str)
    assert isinstance(status_table, str)
    merge_row_to_bigquery(
        build_contract_registration_row(contract, now),
        contract_table,
        merge_key="forecast_contract_hash",
        project_id=project_id,
        update_matched=False,
    )
    merge_row_to_bigquery(
        {
            "forecast_run_id": run_id,
            "forecast_contract_name": contract.name,
            "forecast_contract_hash": contract.hash,
            "run_type": "score",
            "run_status": "succeeded",
            "forecast_origin": rows["forecast_origin"].min(),
            "started_at": prediction_rows["run_at"].min(),
            "finished_at": now,
            "data_cutoff": data_cutoff,
            "source_cutoff_json": cutoff_metadata.get("source_cutoff_json"),
            "feature_availability_hash": cutoff_metadata.get("feature_availability_hash"),
            "feature_materialization_id": cutoff_metadata.get("feature_materialization_id"),
            "feature_version": feature_version,
            "code_sha": code_sha,
            "model_run_id": rows["model_run_id"].iloc[0],
            "model_id": rows["model_id"].iloc[0],
            "config_name": rows["config_name"].iloc[0],
            "row_count": len(rows),
        },
        runs_table,
        merge_key="forecast_run_id",
        project_id=project_id,
        update_matched=False,
    )
    insert_rows_idempotent(
        rows,
        forecast_output_table,
        id_column="forecast_output_id",
        project_id=project_id,
    )
    insert_rows_idempotent(
        build_status_events(rows, changed_at=now, changed_by="forecast-writer"),
        status_table,
        id_column="status_event_id",
        project_id=project_id,
    )
    return len(rows)
