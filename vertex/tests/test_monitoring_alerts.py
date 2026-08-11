"""Monitoring SLO configuration, signal evaluation, and notification routing."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from scripts.evaluate_monitoring_alerts import load_bigquery_rows
from vertex.config.monitoring import load_monitoring_config, validate_monitoring_config
from vertex.monitoring.alerts import evaluate_alerts, route_alerts


@pytest.mark.unit
def test_repository_monitoring_config_is_valid():
    config = load_monitoring_config()

    assert config.slos["publication_freshness"].threshold_minutes == 1440
    assert config.slos["prediction_coverage"].minimum_ratio == 0.98
    assert config.slos["feature_completeness"].minimum_ratio == 0.99
    assert config.slos["realized_calibration"].minimum_ratio == 0.80
    assert config.slos["data_drift"].window_days == 28
    assert config.hash


@pytest.mark.unit
@pytest.mark.parametrize(
    "mutation, match",
    [
        ({"destinations": {}}, "requires destinations"),
        ({"policies": [{"name": "bad", "signal": "unknown"}]}, "invalid signal"),
        (
            {"destinations": {"hook": {"type": "webhook", "minimum_severity": "ticket"}}},
            "requires url_env_var",
        ),
    ],
)
def test_invalid_monitoring_config_is_rejected(mutation, match):
    raw = {
        "destinations": {"log": {"type": "log", "minimum_severity": "ticket"}},
        "slos": {
            "publication_freshness": {
                "owner": "ops",
                "target": 0.99,
                "window_days": 30,
                "threshold_minutes": 120,
            }
        },
        "policies": [
            {
                "name": "stale",
                "signal": "publication_freshness",
                "severity": "page",
                "destination": "log",
            }
        ],
    }
    raw.update(mutation)

    with pytest.raises(ValueError, match=match):
        validate_monitoring_config(raw)


@pytest.mark.unit
def test_evaluate_alerts_emits_only_unhealthy_signals():
    config = load_monitoring_config()
    rows = {
        "data_drift": [
            {"source_model": "stable", "drift_status": "healthy"},
            {"source_model": "new", "drift_status": "insufficient_observations"},
            {"source_model": "shifted", "metric_name": "demand", "drift_status": "drifted"},
        ],
        "delivery_health": [
            {
                "forecast_contract_name": "delivery",
                "delivery_health_status": "failed",
            }
        ],
        "feature_completeness": [
            {"feature_model": "healthy_features", "feature_completeness_status": "healthy"},
            {
                "feature_model": "broken_features",
                "feature_completeness_status": "missing_required_values",
            },
        ],
        "publication_freshness": [
            {"forecast_contract_name": "fresh", "freshness_status": "fresh"},
            {"forecast_contract_name": "stale", "freshness_status": "stale"},
        ],
        "prediction_coverage": [
            {"forecast_contract_name": "low", "coverage_status": "below_threshold"}
        ],
        "pipeline_health": [{"forecast_contract_name": "healthy", "health_status": "healthy"}],
        "realized_calibration": [
            {"forecast_contract_name": "new", "calibration_status": "insufficient_actuals"},
            {"forecast_contract_name": "biased", "calibration_status": "material_bias"},
        ],
    }

    events = evaluate_alerts(config, rows, observed_at=datetime(2026, 8, 10, tzinfo=timezone.utc))

    assert [(event.policy_name, event.resource_key) for event in events] == [
        ("stale_forecast_publication", "stale"),
        ("prediction_coverage_low", "low"),
        ("forecast_features_incomplete", "broken_features"),
        ("forecast_delivery_unhealthy", "delivery"),
        ("forecast_calibration_unreliable", "biased"),
        ("forecast_data_drift_detected", "shifted:demand"),
    ]
    assert route_alerts(config, events) == 6


@pytest.mark.unit
def test_webhook_destination_uses_environment_indirection(monkeypatch):
    config = validate_monitoring_config(
        {
            "destinations": {
                "hook": {
                    "type": "webhook",
                    "minimum_severity": "ticket",
                    "url_env_var": "FORECAST_ALERT_WEBHOOK_URL",
                }
            },
            "slos": {
                "publication_freshness": {
                    "owner": "ops",
                    "target": 0.99,
                    "window_days": 30,
                    "threshold_minutes": 120,
                }
            },
            "policies": [
                {
                    "name": "stale",
                    "signal": "publication_freshness",
                    "severity": "page",
                    "destination": "hook",
                }
            ],
        }
    )
    event = evaluate_alerts(
        config,
        {"publication_freshness": [{"freshness_status": "missing"}]},
    )[0]
    sent = []
    monkeypatch.setenv("FORECAST_ALERT_WEBHOOK_URL", "https://alerts.example.test/hook")

    emitted = route_alerts(
        config, [event], webhook_sender=lambda url, body: sent.append((url, body))
    )

    assert emitted == 1
    assert sent[0][0] == "https://alerts.example.test/hook"
    assert b'"policy_name": "stale"' in sent[0][1]


@pytest.mark.unit
@patch("scripts.evaluate_monitoring_alerts.bigquery.Client")
def test_bigquery_signal_loader_queries_only_validated_monitoring_views(client_class):
    client = MagicMock()
    client_class.return_value = client
    client.query.return_value.to_dataframe.return_value.to_dict.return_value = []

    rows = load_bigquery_rows(project_id="tds-favorita", table_prefix="tds-favorita.favorita")

    assert set(rows) == {
        "data_drift",
        "delivery_health",
        "feature_completeness",
        "publication_freshness",
        "prediction_coverage",
        "pipeline_health",
        "realized_calibration",
    }
    queries = [call.args[0] for call in client.query.call_args_list]
    assert queries == [
        "SELECT * FROM `tds-favorita.favorita.forecast_data_drift`",
        "SELECT * FROM `tds-favorita.favorita.forecast_delivery_health`",
        "SELECT * FROM `tds-favorita.favorita.forecast_feature_completeness`",
        "SELECT * FROM `tds-favorita.favorita.forecast_publication_freshness`",
        "SELECT * FROM `tds-favorita.favorita.forecast_prediction_coverage`",
        "SELECT * FROM `tds-favorita.favorita.forecast_pipeline_health`",
        "SELECT * FROM `tds-favorita.favorita.forecast_realized_calibration`",
    ]
