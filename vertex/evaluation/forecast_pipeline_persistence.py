"""Append-only persistence with forecast-run status as the visibility boundary."""

from __future__ import annotations

from datetime import datetime, timezone

from vertex.config.forecast_contract import ForecastContract
from vertex.evaluation.forecast_pipeline import ForecastPipelineResult, ForecastRunPins
from vertex.utils.bigquery_utils import insert_rows_idempotent, merge_row_to_bigquery
from vertex.utils.data_utils import get_hash
from vertex.utils.forecast_lifecycle import build_status_events
from vertex.utils.forecast_outputs import build_contract_registration_row


def persist_forecast_pipeline_result(
    result: ForecastPipelineResult,
    *,
    contract: ForecastContract,
    pins: ForecastRunPins,
    table_prefix: str,
    actor: str,
    project_id: str | None = None,
) -> None:
    """Persist evidence first and insert the visible draft run record last."""
    if not actor:
        raise ValueError("actor is required")
    merge_row_to_bigquery(
        build_contract_registration_row(contract, datetime.now(timezone.utc)),
        f"{table_prefix}.forecast_contracts",
        merge_key="forecast_contract_hash",
        project_id=project_id,
        update_matched=False,
    )
    insert_rows_idempotent(
        result.stage_records,
        f"{table_prefix}.forecast_pipeline_stage_runs",
        id_column="stage_run_id",
        project_id=project_id,
    )
    insert_rows_idempotent(
        result.validation_checks,
        f"{table_prefix}.forecast_validation_checks",
        id_column="validation_check_id",
        project_id=project_id,
    )
    insert_rows_idempotent(
        result.rows,
        f"{table_prefix}.forecast_outputs",
        id_column="forecast_output_id",
        project_id=project_id,
    )
    now = datetime.now(timezone.utc)
    insert_rows_idempotent(
        build_status_events(result.rows, changed_at=now, changed_by=actor),
        f"{table_prefix}.forecast_status_history",
        id_column="status_event_id",
        project_id=project_id,
    )
    first = result.rows.iloc[0]
    merge_row_to_bigquery(
        {
            "forecast_run_id": result.forecast_run_id,
            "forecast_contract_name": contract.name,
            "forecast_contract_hash": contract.hash,
            "run_type": "scheduled_publication",
            "run_status": "draft",
            "forecast_origin": result.rows["forecast_origin"].min(),
            "started_at": min(record["started_at"] for record in result.stage_records),
            "finished_at": now,
            "data_cutoff": pins.data_cutoff,
            "source_cutoff_json": pins.source_cutoff_json,
            "feature_availability_hash": pins.feature_availability_hash,
            "feature_materialization_id": pins.eligibility_snapshot_id,
            "feature_version": pins.feature_version,
            "code_sha": pins.code_sha,
            "model_run_id": pins.model_run_id,
            "model_id": first["model_id"],
            "config_name": first["config_name"],
            "champion_candidate_id": pins.champion_candidate_id,
            "eligibility_snapshot_id": pins.eligibility_snapshot_id,
            "row_count": len(result.rows),
            "error_message": None,
        },
        f"{table_prefix}.forecast_runs",
        merge_key="forecast_run_id",
        project_id=project_id,
        update_matched=False,
    )


def persist_forecast_pipeline_exception(
    *,
    forecast_run_id: str,
    error: Exception,
    table_prefix: str,
    actor: str,
    project_id: str | None = None,
) -> None:
    """Persist one retry-stable blocking exception for a failed logical run."""
    identity = {
        "forecast_run_id": forecast_run_id,
        "exception_type": "scheduled_publication_failed",
        "error_type": type(error).__name__,
        "error_message": str(error),
    }
    exception_id = get_hash(identity)
    now = datetime.now(timezone.utc)
    insert_rows_idempotent(
        [
            {
                "exception_id": exception_id,
                "idempotency_key": exception_id,
                "forecast_output_id": forecast_run_id,
                "forecast_run_id": forecast_run_id,
                "exception_type": "scheduled_publication_failed",
                "severity": "blocking",
                "exception_status": "open",
                "detected_at": now,
                "detected_by": actor,
                "details_json": identity,
                "resolved_at": None,
                "resolved_by": None,
                "resolution_comment": None,
            }
        ],
        f"{table_prefix}.forecast_exceptions",
        id_column="exception_id",
        project_id=project_id,
    )
