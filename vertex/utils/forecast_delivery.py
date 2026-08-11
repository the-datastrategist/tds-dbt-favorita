"""Deterministic publication and delivery event contracts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from vertex.utils.bigquery_utils import insert_rows_idempotent
from vertex.utils.data_utils import get_hash

DELIVERY_STATUSES = frozenset({"pending", "delivered", "failed", "abandoned"})
PUBLICATION_EVENT_TYPES = frozenset(
    {"forecast.published", "forecast.revised", "forecast.rolled_back"}
)
ALLOWED_DELIVERY_TRANSITIONS = {
    None: frozenset({"pending"}),
    "pending": frozenset({"delivered", "failed", "abandoned"}),
    "failed": frozenset({"pending", "abandoned"}),
    "delivered": frozenset(),
    "abandoned": frozenset(),
}


def build_publication_event(
    *,
    event_type: str,
    forecast_run_id: str,
    forecast_contract_name: str,
    forecast_contract_hash: str,
    publication_version: int,
    destination: str,
    row_count: int,
    actor: str,
    idempotency_key: str,
    prior_version: int | None = None,
    occurred_at: datetime | None = None,
) -> dict[str, Any]:
    """Build one version-level integration event for a complete publication."""
    if event_type not in PUBLICATION_EVENT_TYPES:
        raise ValueError("unsupported publication event_type")
    if publication_version < 1 or row_count < 1:
        raise ValueError("publication_version and row_count must be positive")
    if not all(
        (
            forecast_run_id,
            forecast_contract_name,
            forecast_contract_hash,
            destination,
            actor,
            idempotency_key,
        )
    ):
        raise ValueError("publication event identifiers and actor are required")
    timestamp = occurred_at or datetime.now(timezone.utc)
    identity = {
        "idempotency_key": idempotency_key,
        "event_type": event_type,
        "forecast_run_id": forecast_run_id,
        "publication_version": publication_version,
        "destination": destination,
    }
    payload = {
        "event_type": event_type,
        "forecast_run_id": forecast_run_id,
        "forecast_contract_name": forecast_contract_name,
        "forecast_contract_hash": forecast_contract_hash,
        "publication_version": publication_version,
        "destination": destination,
        "row_count": row_count,
        "occurred_at": timestamp.isoformat(),
    }
    if prior_version is not None:
        payload["prior_version"] = prior_version
    return {
        "publication_event_id": get_hash(identity),
        "idempotency_key": idempotency_key,
        "event_type": event_type,
        "forecast_run_id": forecast_run_id,
        "forecast_contract_name": forecast_contract_name,
        "forecast_contract_hash": forecast_contract_hash,
        "publication_version": publication_version,
        "destination": destination,
        "row_count": row_count,
        "occurred_at": timestamp,
        "occurred_by": actor,
        "payload_json": payload,
    }


def build_delivery_event(
    *,
    forecast_run_id: str,
    publication_version: int,
    destination: str,
    delivery_status: str,
    delivery_attempt: int,
    actor: str,
    idempotency_key: str,
    prior_status: str | None,
    delivery_reference: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    details: dict[str, Any] | None = None,
    occurred_at: datetime | None = None,
) -> dict[str, Any]:
    """Build a validated append-only delivery transition."""
    if delivery_status not in DELIVERY_STATUSES:
        raise ValueError("unsupported delivery_status")
    if prior_status not in ALLOWED_DELIVERY_TRANSITIONS:
        raise ValueError("unsupported prior delivery status")
    if delivery_status not in ALLOWED_DELIVERY_TRANSITIONS[prior_status]:
        raise ValueError(f"invalid delivery transition: {prior_status} -> {delivery_status}")
    if publication_version < 1 or delivery_attempt < 1:
        raise ValueError("publication_version and delivery_attempt must be positive")
    if delivery_status == "delivered" and not delivery_reference:
        raise ValueError("delivered events require delivery_reference")
    if delivery_status == "failed" and not error_message:
        raise ValueError("failed events require error_message")
    if not all((forecast_run_id, destination, actor, idempotency_key)):
        raise ValueError("delivery identifiers and actor are required")
    timestamp = occurred_at or datetime.now(timezone.utc)
    identity = {
        "idempotency_key": idempotency_key,
        "forecast_run_id": forecast_run_id,
        "publication_version": publication_version,
        "destination": destination,
        "delivery_status": delivery_status,
        "delivery_attempt": delivery_attempt,
    }
    return {
        "delivery_event_id": get_hash(identity),
        "idempotency_key": idempotency_key,
        "forecast_run_id": forecast_run_id,
        "publication_version": publication_version,
        "destination": destination,
        "delivery_status": delivery_status,
        "delivery_attempt": delivery_attempt,
        "delivery_reference": delivery_reference,
        "error_code": error_code,
        "error_message": error_message,
        "occurred_at": timestamp,
        "occurred_by": actor,
        "details_json": details,
    }


def persist_publication_event(event: dict[str, Any], *, table_prefix: str, project_id: str) -> None:
    insert_rows_idempotent(
        [event],
        f"{table_prefix}.forecast_publication_events",
        id_column="publication_event_id",
        project_id=project_id,
    )


def persist_delivery_event(event: dict[str, Any], *, table_prefix: str, project_id: str) -> None:
    insert_rows_idempotent(
        [event],
        f"{table_prefix}.forecast_delivery_events",
        id_column="delivery_event_id",
        project_id=project_id,
    )
