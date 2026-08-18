"""Validated SLO, alert-policy, and notification-destination contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

from vertex.utils.data_utils import get_hash

DEFAULT_MONITORING_PATH = Path(__file__).resolve().parent / "monitoring.yaml"
VALID_DESTINATION_TYPES = frozenset({"log", "webhook", "slack"})
VALID_SEVERITIES = ("info", "ticket", "page")
VALID_SIGNALS = frozenset(
    {
        "delivery_health",
        "data_drift",
        "pipeline_cost",
        "feature_completeness",
        "publication_freshness",
        "prediction_coverage",
        "pipeline_health",
        "realized_calibration",
    }
)


@dataclass(frozen=True)
class NotificationDestination:
    name: str
    destination_type: str
    minimum_severity: str
    url_env_var: str | None = None


@dataclass(frozen=True)
class SLODefinition:
    name: str
    owner: str
    target: float
    window_days: int
    threshold_minutes: int | None = None
    minimum_ratio: float | None = None
    maximum_duration_minutes: int | None = None


@dataclass(frozen=True)
class AlertPolicy:
    name: str
    signal: str
    severity: str
    destination: str


@dataclass(frozen=True)
class MonitoringConfig:
    destinations: dict[str, NotificationDestination]
    slos: dict[str, SLODefinition]
    policies: tuple[AlertPolicy, ...]

    @property
    def hash(self) -> str:
        return get_hash(
            {
                "slos": {name: asdict(slo) for name, slo in self.slos.items()},
                "policies": [asdict(policy) for policy in self.policies],
                "destinations": {
                    name: asdict(destination) for name, destination in self.destinations.items()
                },
            }
        )


def _ratio(value: Any, *, field: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not 0 < parsed <= 1:
        raise ValueError(f"{field} must be greater than 0 and no greater than 1")
    return parsed


def _positive_int(value: Any, *, field: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc
    if parsed < 1:
        raise ValueError(f"{field} must be at least 1")
    return parsed


def validate_monitoring_config(raw: dict[str, Any]) -> MonitoringConfig:
    """Validate monitoring configuration and resolve cross-references."""
    raw_destinations = raw.get("destinations")
    raw_slos = raw.get("slos")
    raw_policies = raw.get("policies")
    if not isinstance(raw_destinations, dict) or not raw_destinations:
        raise ValueError("monitoring config requires destinations")
    if not isinstance(raw_slos, dict) or not raw_slos:
        raise ValueError("monitoring config requires slos")
    if not isinstance(raw_policies, list) or not raw_policies:
        raise ValueError("monitoring config requires policies")

    destinations: dict[str, NotificationDestination] = {}
    for name, payload in raw_destinations.items():
        if not isinstance(payload, dict):
            raise ValueError(f"destination {name} must be a mapping")
        destination_type = str(payload.get("type", ""))
        severity = str(payload.get("minimum_severity", ""))
        if destination_type not in VALID_DESTINATION_TYPES:
            raise ValueError(f"destination {name} has invalid type")
        if severity not in VALID_SEVERITIES:
            raise ValueError(f"destination {name} has invalid minimum_severity")
        url_env_var = payload.get("url_env_var")
        if destination_type in {"webhook", "slack"} and not url_env_var:
            raise ValueError(f"{destination_type} destination {name} requires url_env_var")
        destinations[str(name)] = NotificationDestination(
            name=str(name),
            destination_type=destination_type,
            minimum_severity=severity,
            url_env_var=str(url_env_var) if url_env_var else None,
        )

    slos: dict[str, SLODefinition] = {}
    for name, payload in raw_slos.items():
        if not isinstance(payload, dict):
            raise ValueError(f"SLO {name} must be a mapping")
        owner = str(payload.get("owner", "")).strip()
        if not owner:
            raise ValueError(f"SLO {name} requires an owner")
        slos[str(name)] = SLODefinition(
            name=str(name),
            owner=owner,
            target=_ratio(payload.get("target"), field=f"{name}.target"),
            window_days=_positive_int(payload.get("window_days"), field=f"{name}.window_days"),
            threshold_minutes=(
                _positive_int(payload["threshold_minutes"], field=f"{name}.threshold_minutes")
                if payload.get("threshold_minutes") is not None
                else None
            ),
            minimum_ratio=(
                _ratio(payload["minimum_ratio"], field=f"{name}.minimum_ratio")
                if payload.get("minimum_ratio") is not None
                else None
            ),
            maximum_duration_minutes=(
                _positive_int(
                    payload["maximum_duration_minutes"],
                    field=f"{name}.maximum_duration_minutes",
                )
                if payload.get("maximum_duration_minutes") is not None
                else None
            ),
        )

    policies: list[AlertPolicy] = []
    names: set[str] = set()
    for payload in raw_policies:
        if not isinstance(payload, dict):
            raise ValueError("each alert policy must be a mapping")
        name = str(payload.get("name", "")).strip()
        signal = str(payload.get("signal", ""))
        severity = str(payload.get("severity", ""))
        destination = str(payload.get("destination", ""))
        if not name or name in names:
            raise ValueError("alert policy names must be non-empty and unique")
        if signal not in VALID_SIGNALS:
            raise ValueError(f"policy {name} has invalid signal")
        if severity not in VALID_SEVERITIES:
            raise ValueError(f"policy {name} has invalid severity")
        if destination not in destinations:
            raise ValueError(f"policy {name} references unknown destination")
        names.add(name)
        policies.append(AlertPolicy(name, signal, severity, destination))

    return MonitoringConfig(destinations, slos, tuple(policies))


def load_monitoring_config(path: str | Path = DEFAULT_MONITORING_PATH) -> MonitoringConfig:
    with Path(path).open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        raise ValueError("monitoring config root must be a mapping")
    return validate_monitoring_config(raw)
