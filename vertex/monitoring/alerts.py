"""Evaluate normalized warehouse signals and route configurable alerts."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.request import Request, urlopen

from vertex.config.monitoring import VALID_SEVERITIES, MonitoringConfig, NotificationDestination

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class AlertEvent:
    policy_name: str
    signal: str
    severity: str
    destination: str
    resource_key: str
    reason: str
    observed_at: str
    details: dict[str, Any]


def _is_alerting(signal: str, row: dict[str, Any]) -> tuple[bool, str]:
    if signal == "publication_freshness":
        status = str(row.get("freshness_status", "missing"))
        return status != "fresh", status
    if signal == "prediction_coverage":
        status = str(row.get("coverage_status", "missing"))
        return status != "healthy", status
    if signal == "feature_completeness":
        status = str(row.get("feature_completeness_status", "missing"))
        return status != "healthy", status
    if signal == "delivery_health":
        status = str(row.get("delivery_health_status", "missing"))
        return status != "healthy", status
    if signal == "realized_calibration":
        status = str(row.get("calibration_status", "missing"))
        return status not in {"healthy", "insufficient_actuals"}, status
    if signal == "data_drift":
        status = str(row.get("drift_status", "missing"))
        return status not in {"healthy", "insufficient_observations"}, status
    status = str(row.get("health_status", "missing"))
    return status not in {"healthy", "healthy_static"}, status


def evaluate_alerts(
    config: MonitoringConfig,
    signal_rows: dict[str, list[dict[str, Any]]],
    *,
    observed_at: datetime | None = None,
) -> list[AlertEvent]:
    """Convert unhealthy normalized signal rows into deterministic alert events."""
    timestamp = (observed_at or datetime.now(timezone.utc)).isoformat()
    events: list[AlertEvent] = []
    for policy in config.policies:
        for row in signal_rows.get(policy.signal, []):
            alerting, reason = _is_alerting(policy.signal, row)
            if not alerting:
                continue
            if policy.signal == "data_drift":
                resource_key = (
                    f"{row.get('source_model', 'unknown')}:"
                    f"{row.get('metric_name', 'unknown')}"
                )
            else:
                resource_key = str(
                    row.get("forecast_contract_name")
                    or row.get("source_name")
                    or row.get("feature_model")
                    or row.get("forecast_run_id")
                    or "platform"
                )
            events.append(
                AlertEvent(
                    policy_name=policy.name,
                    signal=policy.signal,
                    severity=policy.severity,
                    destination=policy.destination,
                    resource_key=resource_key,
                    reason=reason,
                    observed_at=timestamp,
                    details=row,
                )
            )
    return events


def _severity_enabled(event: AlertEvent, destination: NotificationDestination) -> bool:
    return VALID_SEVERITIES.index(event.severity) >= VALID_SEVERITIES.index(
        destination.minimum_severity
    )


def route_alerts(
    config: MonitoringConfig,
    events: list[AlertEvent],
    *,
    webhook_sender: Callable[[str, bytes], None] | None = None,
) -> int:
    """Route alerts to logs or configured webhooks; return the number emitted."""
    emitted = 0
    for event in events:
        destination = config.destinations[event.destination]
        if not _severity_enabled(event, destination):
            continue
        payload = json.dumps(asdict(event), sort_keys=True, default=str).encode("utf-8")
        if destination.destination_type == "log":
            LOGGER.warning("forecast_monitoring_alert %s", payload.decode("utf-8"))
        else:
            url = os.getenv(destination.url_env_var or "")
            if not url:
                raise ValueError(
                    f"destination {destination.name} requires {destination.url_env_var}"
                )
            if webhook_sender:
                webhook_sender(url, payload)
            else:
                request = Request(url, data=payload, headers={"content-type": "application/json"})
                with urlopen(request, timeout=10):  # nosec B310 - URL is operator configuration
                    pass
        emitted += 1
    return emitted
