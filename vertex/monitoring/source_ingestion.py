"""Append-only source-ingestion evidence and mode-aware health evaluation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from vertex.config.source_monitoring import SourceMonitoringPolicy
from vertex.utils.bigquery_utils import insert_rows_idempotent
from vertex.utils.data_utils import get_hash

VALID_INGESTION_STATUSES = frozenset({"succeeded", "failed", "partial"})


def build_source_ingestion_row(
    *,
    policy: SourceMonitoringPolicy,
    status: str,
    started_at: datetime,
    finished_at: datetime,
    source_watermark: Any | None,
    ingested_row_count: int,
    table_count: int,
    source_uri: str | None = None,
    code_sha: str | None = None,
    error_message: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one immutable ingestion-run record."""
    if status not in VALID_INGESTION_STATUSES:
        raise ValueError(f"status must be one of {sorted(VALID_INGESTION_STATUSES)}")
    if finished_at < started_at:
        raise ValueError("finished_at cannot be earlier than started_at")
    if ingested_row_count < 0 or table_count < 0:
        raise ValueError("ingested_row_count and table_count must be nonnegative")
    if status == "succeeded" and source_watermark is None:
        raise ValueError("successful ingestion requires a source watermark")
    identity = {
        "source_name": policy.source_name,
        "policy_hash": policy.hash,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "source_watermark": str(source_watermark),
        "status": status,
    }
    return {
        "ingestion_run_id": get_hash(identity),
        "source_name": policy.source_name,
        "source_policy_hash": policy.hash,
        "data_mode": policy.data_mode,
        "status": status,
        "started_at": started_at,
        "finished_at": finished_at,
        "source_watermark": source_watermark,
        "ingested_row_count": ingested_row_count,
        "table_count": table_count,
        "source_uri": source_uri,
        "source_table": policy.source_table,
        "watermark_column": policy.watermark_column,
        "expected_interval_hours": policy.expected_interval_hours,
        "allowed_lateness_hours": policy.allowed_lateness_hours,
        "evaluate_on_json": list(policy.evaluate_on),
        "code_sha": code_sha,
        "error_message": error_message,
        "details_json": details or {},
    }


def persist_source_ingestion_row(
    row: dict[str, Any], *, table_id: str, project_id: str | None = None
) -> int:
    """Idempotently append one ingestion record."""
    return insert_rows_idempotent(
        [row], table_id, id_column="ingestion_run_id", project_id=project_id
    )


def evaluate_source_health(
    latest_run: dict[str, Any] | None,
    *,
    evaluated_at: datetime | None = None,
) -> dict[str, Any]:
    """Evaluate operational freshness without treating static event dates as wall-clock time."""
    now = evaluated_at or datetime.now(timezone.utc)
    if latest_run is None:
        return {"health_status": "missing", "is_alerting": True, "reason": "no_ingestion_run"}
    status = str(latest_run.get("status"))
    if status != "succeeded":
        return {
            "health_status": "failed",
            "is_alerting": True,
            "reason": f"latest_ingestion_{status}",
        }
    data_mode = str(latest_run.get("data_mode"))
    if data_mode == "static_demo":
        return {
            "health_status": "healthy_static",
            "is_alerting": False,
            "reason": "static_dataset_freshness_not_applicable",
        }
    if data_mode != "continuous":
        raise ValueError("latest ingestion run has an invalid data_mode")
    finished_at = latest_run.get("finished_at")
    if not isinstance(finished_at, datetime):
        raise ValueError("latest ingestion run requires a datetime finished_at")
    deadline = finished_at + timedelta(
        hours=int(latest_run["expected_interval_hours"]) + int(latest_run["allowed_lateness_hours"])
    )
    if now > deadline:
        return {
            "health_status": "stale",
            "is_alerting": True,
            "reason": "expected_ingestion_window_missed",
            "deadline": deadline,
        }
    return {"health_status": "healthy", "is_alerting": False, "reason": "within_window"}
