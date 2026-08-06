"""Validated source-ingestion and freshness monitoring policies."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from vertex.utils.data_utils import get_hash

DEFAULT_SOURCE_MONITORING_PATH = Path(__file__).resolve().parent / "source_monitoring.yaml"
VALID_DATA_MODES = frozenset({"static_demo", "continuous"})
VALID_EVALUATION_TRIGGERS = frozenset({"watermark_advance", "scheduled", "manual"})


@dataclass(frozen=True)
class SourceMonitoringPolicy:
    """One source's persisted operational expectations."""

    source_name: str
    data_mode: str
    source_table: str
    watermark_column: str
    expected_interval_hours: int
    allowed_lateness_hours: int
    evaluate_on: tuple[str, ...]

    @property
    def hash(self) -> str:
        return get_hash(
            {
                "source_name": self.source_name,
                "data_mode": self.data_mode,
                "source_table": self.source_table,
                "watermark_column": self.watermark_column,
                "expected_interval_hours": self.expected_interval_hours,
                "allowed_lateness_hours": self.allowed_lateness_hours,
                "evaluate_on": list(self.evaluate_on),
            }
        )


def _positive_int(value: Any, *, field: str, allow_zero: bool = False) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc
    minimum = 0 if allow_zero else 1
    if parsed < minimum:
        raise ValueError(f"{field} must be >= {minimum}")
    return parsed


def validate_source_monitoring_config(raw: dict[str, Any]) -> dict[str, SourceMonitoringPolicy]:
    """Validate and normalize a source policy mapping."""
    sources = raw.get("sources")
    if not isinstance(sources, dict) or not sources:
        raise ValueError("source monitoring config requires a non-empty sources mapping")
    policies: dict[str, SourceMonitoringPolicy] = {}
    for source_name, payload in sources.items():
        if not isinstance(payload, dict):
            raise ValueError(f"{source_name}: policy must be a mapping")
        data_mode = str(payload.get("data_mode", ""))
        if data_mode not in VALID_DATA_MODES:
            raise ValueError(f"{source_name}: data_mode must be one of {sorted(VALID_DATA_MODES)}")
        source_table = str(payload.get("source_table", "")).strip()
        watermark_column = str(payload.get("watermark_column", "")).strip()
        if not source_table or not watermark_column:
            raise ValueError(f"{source_name}: source_table and watermark_column are required")
        triggers = tuple(str(value) for value in payload.get("evaluate_on") or [])
        invalid = sorted(set(triggers).difference(VALID_EVALUATION_TRIGGERS))
        if not triggers or invalid:
            suffix = f": {invalid}" if triggers else ""
            raise ValueError(f"{source_name}: invalid or empty evaluate_on{suffix}")
        policies[str(source_name)] = SourceMonitoringPolicy(
            source_name=str(source_name),
            data_mode=data_mode,
            source_table=source_table,
            watermark_column=watermark_column,
            expected_interval_hours=_positive_int(
                payload.get("expected_interval_hours"), field="expected_interval_hours"
            ),
            allowed_lateness_hours=_positive_int(
                payload.get("allowed_lateness_hours", 0),
                field="allowed_lateness_hours",
                allow_zero=True,
            ),
            evaluate_on=triggers,
        )
    return policies


def load_source_monitoring_config(
    path: str | Path = DEFAULT_SOURCE_MONITORING_PATH,
) -> dict[str, SourceMonitoringPolicy]:
    """Load source policies from YAML."""
    with Path(path).open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        raise ValueError("source monitoring config root must be a mapping")
    return validate_source_monitoring_config(raw)
