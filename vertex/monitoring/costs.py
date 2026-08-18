"""Normalized append-only cost evidence for forecast monitoring."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from vertex.utils.bigquery_utils import insert_rows_idempotent
from vertex.utils.data_utils import get_hash


def build_cost_event(
    *,
    service_name: str,
    cost_type: str,
    usage_start_at: datetime,
    usage_end_at: datetime,
    amount_usd: Decimal | str | float,
    source_system: str,
    source_event_id: str,
    forecast_contract_name: str | None = None,
    forecast_run_id: str | None = None,
    model_run_id: str | None = None,
    stage_name: str | None = None,
    environment: str | None = None,
    usage_amount: Decimal | str | float | None = None,
    usage_unit: str | None = None,
    bytes_processed: int | None = None,
    slot_ms: int | None = None,
    labels: dict[str, Any] | None = None,
    recorded_at: datetime | None = None,
) -> dict[str, Any]:
    """Validate and normalize one provider-independent USD cost event."""
    required = {
        "service_name": service_name,
        "cost_type": cost_type,
        "source_system": source_system,
        "source_event_id": source_event_id,
    }
    for field, value in required.items():
        if not str(value).strip():
            raise ValueError(f"{field} must be non-empty")
    if usage_end_at < usage_start_at:
        raise ValueError("usage_end_at cannot be earlier than usage_start_at")
    try:
        amount = Decimal(str(amount_usd))
    except InvalidOperation as exc:
        raise ValueError("amount_usd must be numeric") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError("amount_usd must be finite and nonnegative")
    usage = None
    if usage_amount is not None:
        try:
            usage = Decimal(str(usage_amount))
        except InvalidOperation as exc:
            raise ValueError("usage_amount must be numeric") from exc
        if not usage.is_finite() or usage < 0:
            raise ValueError("usage_amount must be finite and nonnegative")
    if bytes_processed is not None and bytes_processed < 0:
        raise ValueError("bytes_processed must be nonnegative")
    if slot_ms is not None and slot_ms < 0:
        raise ValueError("slot_ms must be nonnegative")
    identity = {"source_system": source_system, "source_event_id": source_event_id}
    return {
        "cost_event_id": get_hash(identity),
        "service_name": service_name,
        "cost_type": cost_type,
        "usage_start_at": usage_start_at,
        "usage_end_at": usage_end_at,
        "amount_usd": str(amount),
        "currency": "USD",
        "forecast_contract_name": forecast_contract_name,
        "forecast_run_id": forecast_run_id,
        "model_run_id": model_run_id,
        "stage_name": stage_name,
        "environment": environment,
        "usage_amount": str(usage) if usage is not None else None,
        "usage_unit": usage_unit,
        "bytes_processed": bytes_processed,
        "slot_ms": slot_ms,
        "source_system": source_system,
        "source_event_id": source_event_id,
        "labels_json": labels or {},
        "recorded_at": recorded_at or datetime.now(timezone.utc),
    }


def persist_cost_event(row: dict[str, Any], *, table_id: str, project_id: str | None = None) -> int:
    """Idempotently append one normalized cost event."""
    return insert_rows_idempotent([row], table_id, id_column="cost_event_id", project_id=project_id)
