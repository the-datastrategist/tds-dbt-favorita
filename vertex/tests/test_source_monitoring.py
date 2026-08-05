"""Source monitoring policy and health semantics."""

from datetime import datetime, timedelta, timezone

import pytest

from vertex.config.source_monitoring import (
    SourceMonitoringPolicy,
    load_source_monitoring_config,
    validate_source_monitoring_config,
)
from vertex.monitoring.source_ingestion import (
    build_source_ingestion_row,
    evaluate_source_health,
)


def _policy(data_mode: str = "static_demo") -> SourceMonitoringPolicy:
    return SourceMonitoringPolicy(
        source_name="favorita_sales",
        data_mode=data_mode,
        source_table="project.raw.sales",
        watermark_column="date",
        expected_interval_hours=24,
        allowed_lateness_hours=6,
        evaluate_on=("watermark_advance", "manual"),
    )


@pytest.mark.unit
def test_repository_policy_is_valid_and_static_demo():
    policy = load_source_monitoring_config()["favorita_sales"]

    assert policy.data_mode == "static_demo"
    assert policy.hash


@pytest.mark.unit
@pytest.mark.parametrize(
    "payload",
    [
        {"data_mode": "batch"},
        {"data_mode": "continuous", "evaluate_on": []},
        {"data_mode": "continuous", "expected_interval_hours": 0},
    ],
)
def test_invalid_policy_is_rejected(payload):
    source = {
        "source_table": "project.raw.sales",
        "watermark_column": "date",
        "expected_interval_hours": 24,
        "allowed_lateness_hours": 0,
        "evaluate_on": ["scheduled"],
        **payload,
    }

    with pytest.raises(ValueError):
        validate_source_monitoring_config({"sources": {"sales": source}})


@pytest.mark.unit
def test_static_demo_does_not_alert_on_historical_watermark():
    finished_at = datetime(2017, 8, 31, tzinfo=timezone.utc)
    row = build_source_ingestion_row(
        policy=_policy(),
        status="succeeded",
        started_at=finished_at,
        finished_at=finished_at,
        source_watermark=finished_at,
        ingested_row_count=125_497_040,
        table_count=1,
    )

    health = evaluate_source_health(row, evaluated_at=datetime(2026, 8, 5, tzinfo=timezone.utc))

    assert health == {
        "health_status": "healthy_static",
        "is_alerting": False,
        "reason": "static_dataset_freshness_not_applicable",
    }


@pytest.mark.unit
def test_continuous_source_alerts_after_cadence_and_grace():
    now = datetime(2026, 8, 5, tzinfo=timezone.utc)
    row = build_source_ingestion_row(
        policy=_policy("continuous"),
        status="succeeded",
        started_at=now - timedelta(hours=31),
        finished_at=now - timedelta(hours=31),
        source_watermark=now - timedelta(hours=31),
        ingested_row_count=100,
        table_count=1,
    )

    health = evaluate_source_health(row, evaluated_at=now)

    assert health["health_status"] == "stale"
    assert health["is_alerting"] is True


@pytest.mark.unit
def test_failed_latest_ingestion_alerts_in_both_modes():
    now = datetime.now(timezone.utc)
    row = build_source_ingestion_row(
        policy=_policy(),
        status="failed",
        started_at=now,
        finished_at=now,
        source_watermark=None,
        ingested_row_count=0,
        table_count=1,
        error_message="load failed",
    )

    assert evaluate_source_health(row)["health_status"] == "failed"


@pytest.mark.unit
def test_successful_ingestion_requires_watermark():
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError, match="requires a source watermark"):
        build_source_ingestion_row(
            policy=_policy(),
            status="succeeded",
            started_at=now,
            finished_at=now,
            source_watermark=None,
            ingested_row_count=1,
            table_count=1,
        )
