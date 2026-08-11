"""Deterministic records for planner overrides, approval, and rollback."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd

from vertex.utils.bigquery_utils import insert_rows_idempotent
from vertex.utils.data_utils import get_hash


def build_override_record(
    forecast_row: dict[str, Any],
    *,
    override_value: float,
    reason_code: str,
    comment: str,
    actor: str,
    idempotency_key: str,
    occurred_at: datetime | None = None,
) -> dict[str, Any]:
    """Build one immutable planner adjustment without changing the canonical row."""
    if override_value < 0:
        raise ValueError("override_value must be nonnegative")
    if not all((reason_code, comment, actor, idempotency_key)):
        raise ValueError("reason_code, comment, actor, and idempotency_key are required")
    timestamp = occurred_at or datetime.now(timezone.utc)
    override_id = get_hash(
        {
            "idempotency_key": idempotency_key,
            "forecast_output_id": forecast_row["forecast_output_id"],
            "override_value": float(override_value),
        }
    )
    return {
        "override_id": override_id,
        "idempotency_key": idempotency_key,
        "forecast_output_id": forecast_row["forecast_output_id"],
        "forecast_run_id": forecast_row["forecast_run_id"],
        "override_value": float(override_value),
        "reason_code": reason_code,
        "comment": comment,
        "overridden_at": timestamp,
        "overridden_by": actor,
    }


def build_manual_publication_records(
    forecast_rows: pd.DataFrame,
    *,
    overrides: pd.DataFrame | None,
    actor: str,
    destination: str,
    idempotency_key: str,
    publication_version: int,
    reason_code: str,
    comment: str,
    occurred_at: datetime | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Approve and publish a complete run, selecting at most one override per output."""
    if forecast_rows.empty:
        raise ValueError("forecast_rows cannot be empty")
    if publication_version < 1:
        raise ValueError("publication_version must be positive")
    if not all((actor, destination, idempotency_key, reason_code, comment)):
        raise ValueError(
            "actor, destination, idempotency_key, reason_code, and comment are required"
        )
    override_by_output: dict[str, dict[str, Any]] = {}
    if overrides is not None and not overrides.empty:
        if overrides["forecast_output_id"].duplicated().any():
            raise ValueError("at most one selected override is allowed per forecast output")
        override_by_output = {
            str(row["forecast_output_id"]): row for row in overrides.to_dict(orient="records")
        }
    timestamp = occurred_at or datetime.now(timezone.utc)
    approvals: list[dict[str, Any]] = []
    publications: list[dict[str, Any]] = []
    for row in forecast_rows.to_dict(orient="records"):
        selected = override_by_output.get(str(row["forecast_output_id"]))
        value = float(selected["override_value"] if selected else row["prediction_p50"])
        approval_id = get_hash(
            {
                "idempotency_key": idempotency_key,
                "forecast_output_id": row["forecast_output_id"],
                "override_id": selected["override_id"] if selected else None,
            }
        )
        publication_id = get_hash(
            {
                "idempotency_key": idempotency_key,
                "forecast_output_id": row["forecast_output_id"],
                "publication_version": publication_version,
                "destination": destination,
            }
        )
        approvals.append(
            {
                "approval_id": approval_id,
                "idempotency_key": idempotency_key,
                "forecast_output_id": row["forecast_output_id"],
                "forecast_run_id": row["forecast_run_id"],
                "override_id": selected["override_id"] if selected else None,
                "decision": "approved",
                "approved_value": value,
                "reason_code": reason_code,
                "comment": comment,
                "decided_at": timestamp,
                "decided_by": actor,
            }
        )
        publications.append(
            {
                "publication_id": publication_id,
                "idempotency_key": idempotency_key,
                "forecast_output_id": row["forecast_output_id"],
                "forecast_run_id": row["forecast_run_id"],
                "approval_id": approval_id,
                "publication_version": publication_version,
                "published_value": value,
                "destination": destination,
                "delivery_status": "pending",
                "delivery_reference": None,
                "published_at": timestamp,
                "published_by": actor,
            }
        )
    return approvals, publications


def build_rollback_records(
    prior_publications: pd.DataFrame,
    *,
    actor: str,
    idempotency_key: str,
    reason_code: str,
    comment: str,
    new_version: int,
    occurred_at: datetime | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Republish prior values as a new version and retain supersession lineage."""
    if prior_publications.empty:
        raise ValueError("prior_publications cannot be empty")
    if new_version <= int(prior_publications["publication_version"].max()):
        raise ValueError("new_version must exceed the selected prior publication version")
    timestamp = occurred_at or datetime.now(timezone.utc)
    forecast_rows = prior_publications.rename(columns={"published_value": "prediction_p50"})
    approvals, replacements = build_manual_publication_records(
        forecast_rows,
        overrides=None,
        actor=actor,
        destination=str(prior_publications.iloc[0]["destination"]),
        idempotency_key=idempotency_key,
        publication_version=new_version,
        reason_code=reason_code,
        comment=comment,
        occurred_at=timestamp,
    )
    replacement_by_output = {row["forecast_output_id"]: row for row in replacements}
    revisions = []
    for prior in prior_publications.to_dict(orient="records"):
        replacement = replacement_by_output[prior["forecast_output_id"]]
        revisions.append(
            {
                "revision_id": get_hash(
                    {
                        "idempotency_key": idempotency_key,
                        "prior_publication_id": prior["publication_id"],
                        "replacement_publication_id": replacement["publication_id"],
                    }
                ),
                "idempotency_key": idempotency_key,
                "forecast_output_id": prior["forecast_output_id"],
                "forecast_run_id": prior["forecast_run_id"],
                "prior_publication_id": prior["publication_id"],
                "replacement_publication_id": replacement["publication_id"],
                "revision_type": "rollback",
                "reason_code": reason_code,
                "comment": comment,
                "revised_at": timestamp,
                "revised_by": actor,
            }
        )
    return approvals, replacements, revisions


def build_revision_records(
    prior_publications: pd.DataFrame,
    replacement_publications: list[dict[str, Any]],
    *,
    actor: str,
    idempotency_key: str,
    reason_code: str,
    comment: str,
    occurred_at: datetime | None = None,
) -> list[dict[str, Any]]:
    """Link one complete publication version to its approved replacement."""
    replacement_by_output = {row["forecast_output_id"]: row for row in replacement_publications}
    if prior_publications.empty or set(prior_publications["forecast_output_id"]) != set(
        replacement_by_output
    ):
        raise ValueError("revision requires complete matching prior and replacement versions")
    timestamp = occurred_at or datetime.now(timezone.utc)
    records = []
    for prior in prior_publications.to_dict(orient="records"):
        replacement = replacement_by_output[prior["forecast_output_id"]]
        records.append(
            {
                "revision_id": get_hash(
                    {
                        "idempotency_key": idempotency_key,
                        "prior_publication_id": prior["publication_id"],
                        "replacement_publication_id": replacement["publication_id"],
                    }
                ),
                "idempotency_key": idempotency_key,
                "forecast_output_id": prior["forecast_output_id"],
                "forecast_run_id": prior["forecast_run_id"],
                "prior_publication_id": prior["publication_id"],
                "replacement_publication_id": replacement["publication_id"],
                "revision_type": "supersede",
                "reason_code": reason_code,
                "comment": comment,
                "revised_at": timestamp,
                "revised_by": actor,
            }
        )
    return records


def persist_operation_records(
    *,
    table_prefix: str,
    project_id: str,
    overrides: list[dict[str, Any]] | None = None,
    approvals: list[dict[str, Any]] | None = None,
    publications: list[dict[str, Any]] | None = None,
    revisions: list[dict[str, Any]] | None = None,
) -> None:
    """Insert operation records idempotently in dependency order."""
    for rows, table, id_column in (
        (overrides, "forecast_overrides", "override_id"),
        (approvals, "forecast_approvals", "approval_id"),
        (publications, "forecast_publications", "publication_id"),
        (revisions, "forecast_revisions", "revision_id"),
    ):
        if rows:
            insert_rows_idempotent(
                rows,
                f"{table_prefix}.{table}",
                id_column=id_column,
                project_id=project_id,
            )
