"""Normalized forecast-cost evidence tests."""

from datetime import datetime, timedelta, timezone

import pytest

from vertex.monitoring.costs import build_cost_event


@pytest.mark.unit
def test_cost_event_is_normalized_and_retry_stable():
    start = datetime(2026, 8, 10, tzinfo=timezone.utc)
    kwargs = {
        "service_name": "bigquery",
        "cost_type": "query",
        "usage_start_at": start,
        "usage_end_at": start + timedelta(minutes=1),
        "amount_usd": "1.25",
        "source_system": "billing_export",
        "source_event_id": "invoice-line-1",
        "forecast_contract_name": "daily_store",
        "forecast_run_id": "run-1",
        "model_run_id": "model-1",
        "stage_name": "score",
        "environment": "dev",
        "usage_amount": "2048",
        "usage_unit": "bytes",
        "bytes_processed": 2048,
        "slot_ms": 120,
    }

    first = build_cost_event(**kwargs)
    retry = build_cost_event(**kwargs)

    assert first["cost_event_id"] == retry["cost_event_id"]
    assert first["amount_usd"] == "1.25"
    assert first["currency"] == "USD"
    assert first["usage_amount"] == "2048"
    assert first["bytes_processed"] == 2048
    assert first["slot_ms"] == 120


@pytest.mark.unit
@pytest.mark.parametrize("amount", ["-1", "NaN", "Infinity"])
def test_cost_event_rejects_invalid_amount(amount):
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError, match="finite and nonnegative"):
        build_cost_event(
            service_name="bigquery",
            cost_type="query",
            usage_start_at=now,
            usage_end_at=now,
            amount_usd=amount,
            source_system="test",
            source_event_id="bad",
        )


@pytest.mark.unit
def test_cost_event_rejects_reversed_usage_window():
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError, match="cannot be earlier"):
        build_cost_event(
            service_name="vertex_ai",
            cost_type="training",
            usage_start_at=now,
            usage_end_at=now - timedelta(seconds=1),
            amount_usd="1",
            source_system="test",
            source_event_id="reversed",
        )


@pytest.mark.unit
@pytest.mark.parametrize(
    "field,value,match",
    [
        ("usage_amount", "-1", "usage_amount must be finite and nonnegative"),
        ("bytes_processed", -1, "bytes_processed must be nonnegative"),
        ("slot_ms", -1, "slot_ms must be nonnegative"),
    ],
)
def test_cost_event_rejects_invalid_usage(field, value, match):
    now = datetime.now(timezone.utc)
    kwargs = {
        "service_name": "bigquery",
        "cost_type": "query",
        "usage_start_at": now,
        "usage_end_at": now,
        "amount_usd": "1",
        "source_system": "test",
        "source_event_id": "bad-usage",
        field: value,
    }
    with pytest.raises(ValueError, match=match):
        build_cost_event(**kwargs)
