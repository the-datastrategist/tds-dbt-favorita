"""Canonical forecast output row schema and builders."""

from __future__ import annotations

import json
from typing import Any, Optional

import pandas as pd

from vertex.config.forecast_contract import ForecastContract, load_forecast_contract
from vertex.config.feature_availability import feature_cutoff_metadata_from_frame
from vertex.utils.bigquery_utils import load_to_bigquery
from vertex.utils.data_utils import get_hash
from vertex.utils.run_context import get_git_sha

FORECAST_OUTPUT_COLUMNS = [
    "forecast_output_id",
    "source_prediction_id",
    "forecast_run_id",
    "forecast_contract_name",
    "forecast_contract_hash",
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
    if "forecast_date" in work.columns:
        target_date = work["forecast_date"].where(work["forecast_date"].notna(), work["date"])
    else:
        target_date = work["date"]
    horizon = work.get("forecast_horizon")
    if horizon is None:
        horizon = pd.Series([None] * len(work), index=work.index, dtype=object)
    else:
        horizon = horizon.where(horizon.notna(), None).astype(object)

    dimensions = [col for col in contract.dimensions if col in work.columns]
    if not dimensions and "entity_id" in work.columns:
        dimensions = ["entity_id"]

    entity_keys = work.apply(lambda row: _json_safe_entity(row, dimensions), axis=1)
    forecast_run_ids = work["predict_run_id"]
    created_at = work["run_at"]

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
        for run_id, entity_key, target, h in zip(forecast_run_ids, entity_keys, target_date, horizon)
    ]

    frame = pd.DataFrame(
        {
            "forecast_output_id": output_ids,
            "source_prediction_id": work["prediction_id"],
            "forecast_run_id": forecast_run_ids,
            "forecast_contract_name": contract.name,
            "forecast_contract_hash": contract.hash,
            "forecast_origin": work["run_at"],
            "target_date": target_date,
            "horizon": horizon,
            "grain": ",".join(contract.dimensions),
            "entity_key_json": entity_keys,
            "target": contract.target,
            "target_unit": contract.target_unit,
            "prediction_p10": work.get("prediction_lower"),
            "prediction_p50": work["prediction"],
            "prediction_p90": work.get("prediction_upper"),
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


def write_forecast_outputs_if_configured(
    *,
    config: dict[str, Any],
    prediction_rows: pd.DataFrame,
    project_id: Optional[str] = None,
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
    cutoff_metadata = feature_cutoff_metadata_from_frame(
        prediction_rows,
        date_column="date",
    )
    rows = build_forecast_output_rows(
        prediction_rows,
        contract=contract,
        feature_version=inputs.get("feature_version") or inputs.get("feature_table_version"),
        code_sha=get_git_sha(),
        data_cutoff=inputs.get("data_cutoff")
        or cutoff_metadata.get("data_cutoff")
        or prediction_rows["run_at"].max(),
        forecast_status=outputs.get("forecast_status", "draft"),
    )
    load_to_bigquery(
        data=rows,
        table_id=forecast_output_table,
        project_id=project_id,
        if_exists="append",
    )
    return len(rows)
