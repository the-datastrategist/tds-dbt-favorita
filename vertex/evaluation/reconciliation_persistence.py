"""Idempotent persistence for hierarchy reconciliation runs and outputs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd

from vertex.config.hierarchy import HierarchyConfig
from vertex.utils.bigquery_utils import insert_rows_idempotent
from vertex.utils.data_utils import get_hash


def build_reconciliation_records(
    reconciled: pd.DataFrame,
    *,
    config: HierarchyConfig,
    forecast_run_id: str,
    reconciliation_run_id: str | None = None,
    started_at: datetime | None = None,
) -> tuple[dict[str, Any], pd.DataFrame]:
    """Build deterministic run and output records from reconciled forecasts."""
    required = {
        "node_id",
        "level_name",
        "forecast_origin",
        "target_date",
        "horizon",
        "base_prediction_p10",
        "base_prediction_p50",
        "base_prediction_p90",
        "prediction_p10",
        "prediction_p50",
        "prediction_p90",
        "reconciliation_method",
    }
    if missing := sorted(required.difference(reconciled.columns)):
        raise ValueError(f"reconciled forecasts are missing required columns: {missing}")
    if reconciled.empty:
        raise ValueError("reconciled forecasts cannot be empty")
    methods = reconciled["reconciliation_method"].dropna().unique().tolist()
    if methods != [config.method]:
        raise ValueError("reconciled forecast method does not match hierarchy config")
    started = started_at or datetime.now(timezone.utc)
    run_id = reconciliation_run_id or get_hash(
        {
            "forecast_run_id": forecast_run_id,
            "hierarchy_hash": config.hash,
            "method": config.method,
        }
    )
    output = reconciled.copy()
    output["reconciliation_run_id"] = run_id
    output["forecast_run_id"] = forecast_run_id
    output["hierarchy_name"] = config.name
    output["hierarchy_version"] = config.version
    output["created_at"] = started
    if "forecast_output_id" not in output:
        output["forecast_output_id"] = None
    output["reconciliation_output_id"] = [
        get_hash(
            {
                "reconciliation_run_id": run_id,
                "node_id": row.node_id,
                "forecast_origin": str(row.forecast_origin),
                "target_date": str(row.target_date),
                "horizon": int(row.horizon),
            }
        )
        for row in output.itertuples()
    ]
    columns = [
        "reconciliation_output_id",
        "reconciliation_run_id",
        "forecast_output_id",
        "forecast_run_id",
        "hierarchy_name",
        "hierarchy_version",
        "node_id",
        "level_name",
        "forecast_origin",
        "target_date",
        "horizon",
        "base_prediction_p10",
        "base_prediction_p50",
        "base_prediction_p90",
        "prediction_p10",
        "prediction_p50",
        "prediction_p90",
        "reconciliation_method",
        "created_at",
    ]
    run = {
        "reconciliation_run_id": run_id,
        "forecast_run_id": forecast_run_id,
        "hierarchy_name": config.name,
        "hierarchy_version": config.version,
        "reconciliation_method": config.method,
        "tolerance_abs": config.tolerance_abs,
        "run_status": "completed",
        "input_row_count": len(output),
        "output_row_count": len(output),
        "violation_count": 0,
        "started_at": started,
        "finished_at": datetime.now(timezone.utc),
        "error_message": None,
    }
    return run, output[columns]


def persist_reconciliation_records(
    run: dict[str, Any],
    outputs: pd.DataFrame,
    *,
    run_table: str,
    output_table: str,
    project_id: str | None = None,
) -> None:
    """Persist reconciliation data with insert-only deterministic keys."""
    insert_rows_idempotent(
        [run],
        run_table,
        id_column="reconciliation_run_id",
        project_id=project_id,
    )
    insert_rows_idempotent(
        outputs,
        output_table,
        id_column="reconciliation_output_id",
        project_id=project_id,
    )
