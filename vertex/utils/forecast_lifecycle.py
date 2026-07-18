"""Validated, append-only forecast lifecycle events."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from vertex.utils.data_utils import get_hash

FORECAST_STATUSES = frozenset({"draft", "approved", "published", "superseded", "failed"})
ALLOWED_TRANSITIONS = {
    None: frozenset({"draft", "failed"}),
    "draft": frozenset({"approved", "superseded", "failed"}),
    "approved": frozenset({"published", "superseded", "failed"}),
    "published": frozenset({"superseded"}),
    "superseded": frozenset(),
    "failed": frozenset(),
}


def validate_forecast_status(status: str) -> None:
    if status not in FORECAST_STATUSES:
        raise ValueError(f"invalid forecast status {status!r}")


def validate_status_transition(previous_status: str | None, new_status: str) -> None:
    if previous_status is not None:
        validate_forecast_status(previous_status)
    validate_forecast_status(new_status)
    if new_status not in ALLOWED_TRANSITIONS[previous_status]:
        raise ValueError(
            f"invalid forecast status transition: {previous_status!r} -> {new_status!r}"
        )


def build_status_events(
    forecast_rows: pd.DataFrame,
    *,
    changed_at: datetime,
    changed_by: str,
    previous_status: str | None = None,
    reason_code: str | None = None,
    comment: str | None = None,
) -> list[dict[str, Any]]:
    """Build stable lifecycle events; retries produce the same event IDs."""
    if not changed_by:
        raise ValueError("changed_by is required for forecast lifecycle events")
    events: list[dict[str, Any]] = []
    for row in forecast_rows.to_dict(orient="records"):
        new_status = row["forecast_status"]
        validate_status_transition(previous_status, new_status)
        payload = {
            "forecast_output_id": row["forecast_output_id"],
            "forecast_run_id": row["forecast_run_id"],
            "previous_status": previous_status,
            "new_status": new_status,
        }
        events.append(
            {
                "status_event_id": get_hash(payload),
                **payload,
                "changed_at": changed_at,
                "changed_by": changed_by,
                "reason_code": reason_code,
                "comment": comment,
            }
        )
    return events
