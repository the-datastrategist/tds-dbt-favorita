"""Tests for append-only planner and revision operations."""

from datetime import datetime, timezone

import pandas as pd
import pytest

from vertex.utils.forecast_operations import (
    build_manual_publication_records,
    build_override_record,
    build_revision_records,
    build_rollback_records,
)

NOW = datetime(2026, 8, 10, tzinfo=timezone.utc)


def _rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "forecast_output_id": f"output-{index}",
                "forecast_run_id": "run-1",
                "prediction_p50": float(index * 10),
            }
            for index in (1, 2)
        ]
    )


@pytest.mark.unit
def test_override_is_deterministic_and_preserves_canonical_value():
    row = _rows().iloc[0].to_dict()
    first = build_override_record(
        row,
        override_value=12,
        reason_code="planner_context",
        comment="Local event",
        actor="planner@example.com",
        idempotency_key="override-1",
        occurred_at=NOW,
    )
    retry = build_override_record(
        row,
        override_value=12,
        reason_code="planner_context",
        comment="Local event",
        actor="planner@example.com",
        idempotency_key="override-1",
        occurred_at=NOW,
    )
    assert first == retry
    assert first["override_value"] == 12
    assert row["prediction_p50"] == 10


@pytest.mark.unit
def test_manual_publication_selects_override_and_is_idempotent():
    rows = _rows()
    override = build_override_record(
        rows.iloc[0].to_dict(),
        override_value=12,
        reason_code="planner_context",
        comment="Local event",
        actor="planner@example.com",
        idempotency_key="override-1",
        occurred_at=NOW,
    )
    kwargs = dict(
        overrides=pd.DataFrame([override]),
        actor="approver@example.com",
        destination="canonical_bigquery",
        idempotency_key="publish-1",
        publication_version=1,
        reason_code="review_complete",
        comment="Approved",
        occurred_at=NOW,
    )
    first = build_manual_publication_records(rows, **kwargs)
    assert first == build_manual_publication_records(rows, **kwargs)
    approvals, publications = first
    assert [row["approved_value"] for row in approvals] == [12, 20]
    assert [row["published_value"] for row in publications] == [12, 20]
    assert approvals[0]["override_id"] == override["override_id"]
    assert approvals[1]["override_id"] is None


@pytest.mark.unit
def test_rollback_republishes_prior_values_as_new_version():
    rows = _rows()
    _, prior = build_manual_publication_records(
        rows,
        overrides=None,
        actor="approver@example.com",
        destination="canonical_bigquery",
        idempotency_key="publish-1",
        publication_version=1,
        reason_code="review_complete",
        comment="Approved",
        occurred_at=NOW,
    )
    approvals, replacements, revisions = build_rollback_records(
        pd.DataFrame(prior),
        actor="operator@example.com",
        idempotency_key="rollback-1",
        reason_code="bad_revision",
        comment="Restore version 1",
        new_version=3,
        occurred_at=NOW,
    )
    assert len(approvals) == len(replacements) == len(revisions) == 2
    assert {row["publication_version"] for row in replacements} == {3}
    assert [row["published_value"] for row in replacements] == [10, 20]
    assert all(row["revision_type"] == "rollback" for row in revisions)
    assert revisions[0]["replacement_publication_id"] == replacements[0]["publication_id"]


@pytest.mark.unit
def test_revision_links_complete_prior_and_replacement_versions():
    rows = _rows()
    common = dict(
        overrides=None,
        actor="approver@example.com",
        destination="canonical_bigquery",
        reason_code="review_complete",
        comment="Approved",
        occurred_at=NOW,
    )
    _, prior = build_manual_publication_records(
        rows, idempotency_key="publish-1", publication_version=1, **common
    )
    _, replacement = build_manual_publication_records(
        rows, idempotency_key="revision-2", publication_version=2, **common
    )
    revisions = build_revision_records(
        pd.DataFrame(prior),
        replacement,
        actor="approver@example.com",
        idempotency_key="revision-2",
        reason_code="new_information",
        comment="Replace version 1",
        occurred_at=NOW,
    )
    assert len(revisions) == 2
    assert {row["revision_type"] for row in revisions} == {"supersede"}
    assert revisions[0]["prior_publication_id"] == prior[0]["publication_id"]


@pytest.mark.unit
def test_negative_override_is_rejected():
    with pytest.raises(ValueError, match="nonnegative"):
        build_override_record(
            _rows().iloc[0].to_dict(),
            override_value=-1,
            reason_code="planner_context",
            comment="Invalid",
            actor="planner@example.com",
            idempotency_key="override-1",
        )
