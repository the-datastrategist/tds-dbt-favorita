"""Version-level publication and delivery event behavior."""

from datetime import datetime, timezone

import pytest

from vertex.utils.forecast_delivery import build_delivery_event, build_publication_event

NOW = datetime(2026, 8, 11, tzinfo=timezone.utc)
COMMON = {
    "forecast_run_id": "run-1",
    "publication_version": 3,
    "destination": "canonical_bigquery",
    "actor": "operator@example.com",
}


@pytest.mark.unit
def test_publication_event_is_version_level_and_retry_stable():
    kwargs = dict(
        event_type="forecast.rolled_back",
        forecast_contract_name="contract-1",
        forecast_contract_hash="hash-1",
        row_count=55,
        idempotency_key="rollback-v3",
        prior_version=1,
        occurred_at=NOW,
        **COMMON,
    )
    event = build_publication_event(**kwargs)
    assert event == build_publication_event(**kwargs)
    assert event["row_count"] == 55
    assert event["payload_json"]["prior_version"] == 1


@pytest.mark.unit
def test_delivery_lifecycle_is_append_only_and_retry_stable():
    pending = build_delivery_event(
        delivery_status="pending",
        delivery_attempt=1,
        prior_status=None,
        idempotency_key="delivery-start",
        occurred_at=NOW,
        **COMMON,
    )
    failed = build_delivery_event(
        delivery_status="failed",
        delivery_attempt=1,
        prior_status="pending",
        idempotency_key="delivery-failed",
        error_code="DOWNSTREAM_503",
        error_message="consumer unavailable",
        occurred_at=NOW,
        **COMMON,
    )
    retry = build_delivery_event(
        delivery_status="pending",
        delivery_attempt=2,
        prior_status="failed",
        idempotency_key="delivery-retry",
        occurred_at=NOW,
        **COMMON,
    )
    delivered = build_delivery_event(
        delivery_status="delivered",
        delivery_attempt=2,
        prior_status="pending",
        idempotency_key="delivery-confirm",
        delivery_reference="gs://bucket/object.parquet",
        occurred_at=NOW,
        **COMMON,
    )
    assert pending == build_delivery_event(
        delivery_status="pending",
        delivery_attempt=1,
        prior_status=None,
        idempotency_key="delivery-start",
        occurred_at=NOW,
        **COMMON,
    )
    assert [
        pending["delivery_status"],
        failed["delivery_status"],
        retry["delivery_status"],
        delivered["delivery_status"],
    ] == [
        "pending",
        "failed",
        "pending",
        "delivered",
    ]


@pytest.mark.unit
def test_delivery_rejects_invalid_terminal_transition_and_missing_evidence():
    with pytest.raises(ValueError, match="invalid delivery transition"):
        build_delivery_event(
            delivery_status="failed",
            delivery_attempt=2,
            prior_status="delivered",
            idempotency_key="bad",
            error_message="late failure",
            **COMMON,
        )
    with pytest.raises(ValueError, match="delivery_reference"):
        build_delivery_event(
            delivery_status="delivered",
            delivery_attempt=1,
            prior_status="pending",
            idempotency_key="missing-reference",
            **COMMON,
        )
