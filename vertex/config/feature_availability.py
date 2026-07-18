"""Feature availability registry and point-in-time validation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

import pandas as pd
import yaml

from vertex.utils.data_utils import get_hash

DEFAULT_FEATURE_AVAILABILITY_PATH = Path(__file__).resolve().parent / "feature_availability.yaml"

ALLOWED_AVAILABILITY = frozenset(
    {
        "known_future",
        "observed_lagged",
        "observed_after_period",
        "forecasted_external",
        "planned_revisable",
        "static_master_data",
    }
)

KNOWN_FUTURE_AVAILABILITY = frozenset(
    {"known_future", "forecasted_external", "planned_revisable", "static_master_data"}
)
OBSERVED_AVAILABILITY = frozenset({"observed_lagged", "observed_after_period"})
KNOWN_FUTURE_METADATA_FIELDS = frozenset(
    {"timestamp_column", "source_cutoff_column", "plan_version_column", "materialization_column"}
)


@dataclass(frozen=True)
class FeatureAvailabilityEntry:
    """Registry entry for an exact feature name or pattern match."""

    name: str
    availability: str
    source_model: Optional[str] = None
    timestamp_column: Optional[str] = None
    source_cutoff_column: Optional[str] = None
    plan_version_column: Optional[str] = None
    materialization_column: Optional[str] = None
    max_target_lag_days: Optional[int] = None
    pattern: Optional[str] = None

    @property
    def has_known_future_metadata(self) -> bool:
        return any(getattr(self, field, None) for field in KNOWN_FUTURE_METADATA_FIELDS)


@dataclass(frozen=True)
class FeatureAvailabilityRegistry:
    """Validated feature availability registry with exact and pattern lookups."""

    raw: dict[str, Any]
    features: dict[str, FeatureAvailabilityEntry]
    patterns: tuple[FeatureAvailabilityEntry, ...]

    @property
    def hash(self) -> str:
        return get_hash(self.raw)

    def match(self, feature_name: str) -> FeatureAvailabilityEntry | None:
        if feature_name in self.features:
            return self.features[feature_name]
        for entry in self.patterns:
            if entry.pattern and re.match(entry.pattern, feature_name):
                return entry
        return None

    def validate_features(
        self,
        feature_names: Iterable[str],
        *,
        context: str = "model features",
    ) -> None:
        """Validate that concrete model feature names are registered and PIT-safe."""
        unregistered: list[str] = []
        leaking: list[str] = []
        for feature_name in sorted(set(feature_names)):
            entry = self.match(feature_name)
            if entry is None:
                unregistered.append(feature_name)
                continue
            if entry.availability == "observed_after_period":
                leaking.append(feature_name)
        if unregistered:
            raise ValueError(f"Unregistered {context}: {', '.join(unregistered[:20])}")
        if leaking:
            raise ValueError(
                "Observed-after-period features cannot be used as model inputs: "
                f"{', '.join(leaking[:20])}"
            )

    def validate_forecast_contract(self, contract_spec: dict[str, Any]) -> None:
        """Validate contract feature declarations against the registry."""
        known_future = list(contract_spec.get("known_future_features") or [])
        observed = list(contract_spec.get("observed_features") or [])
        errors: list[str] = []

        for feature_name in known_future:
            entry = self.match(feature_name)
            if entry is None:
                errors.append(f"{feature_name}: not registered")
                continue
            if entry.availability not in KNOWN_FUTURE_AVAILABILITY:
                errors.append(
                    f"{feature_name}: availability {entry.availability!r} is not known-future safe"
                )
            if entry.availability in {"known_future", "forecasted_external", "planned_revisable"}:
                if not entry.has_known_future_metadata:
                    errors.append(f"{feature_name}: missing source cutoff or plan metadata")

        for feature_name in observed:
            entry = self.match(feature_name)
            if entry is None:
                errors.append(f"{feature_name}: not registered")
                continue
            if entry.availability not in OBSERVED_AVAILABILITY:
                errors.append(
                    f"{feature_name}: availability {entry.availability!r} is not observed"
                )

        if errors:
            raise ValueError("Invalid forecast contract feature availability: " + "; ".join(errors))

    def validate_frame_cutoffs(
        self,
        df: pd.DataFrame,
        feature_names: Iterable[str],
        *,
        cutoff: Any | pd.Series,
        date_column: str | None = None,
        context: str = "feature frame",
    ) -> dict[str, Any]:
        """Reject feature snapshots whose source metadata was not available at cutoff."""
        if df.empty:
            raise ValueError(f"{context} cannot enforce cutoffs on an empty feature frame")
        self.validate_features(feature_names, context=context)
        entries = [self.match(name) for name in sorted(set(feature_names))]
        metadata_columns = sorted(
            {
                str(getattr(entry, field))
                for entry in entries
                if entry is not None
                for field in KNOWN_FUTURE_METADATA_FIELDS
                if getattr(entry, field, None)
            }
        )

        if isinstance(cutoff, pd.Series):
            cutoff_values = pd.to_datetime(cutoff.reindex(df.index), errors="coerce")
        else:
            cutoff_values = pd.Series(pd.to_datetime(cutoff), index=df.index)
        if cutoff_values.isna().any():
            raise ValueError(f"{context} has missing or invalid forecast cutoffs")

        source_cutoffs: dict[str, str] = {}
        for column in metadata_columns:
            if column not in df.columns:
                raise ValueError(f"{context} is missing point-in-time metadata column {column!r}")
            values = pd.to_datetime(df[column], errors="coerce")
            if values.isna().any():
                raise ValueError(f"{context} has null or invalid values in {column!r}")
            leaking = values.gt(cutoff_values)
            if leaking.any():
                first_index = leaking[leaking].index[0]
                raise ValueError(
                    f"{context} violates forecast cutoff: {column}="
                    f"{values.loc[first_index].isoformat()} is later than "
                    f"{cutoff_values.loc[first_index].isoformat()}"
                )
            source_cutoffs[column] = values.max().to_pydatetime().isoformat()

        if date_column:
            if date_column not in df.columns:
                raise ValueError(f"{context} is missing cutoff date column {date_column!r}")
            dates = pd.to_datetime(df[date_column], errors="coerce")
            if dates.isna().any() or dates.gt(cutoff_values).any():
                raise ValueError(f"{context} contains rows later than their forecast cutoff")
            source_cutoffs.setdefault(date_column, dates.max().to_pydatetime().isoformat())

        return {
            "data_cutoff": cutoff_values.max().to_pydatetime().isoformat(),
            "source_cutoff_json": source_cutoffs,
            "feature_availability_hash": self.hash,
        }


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Feature availability registry not found: {path}")
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping at root of {path}")
    return data


def _entry_from_mapping(
    name: str,
    payload: dict[str, Any],
    *,
    pattern: Optional[str] = None,
) -> FeatureAvailabilityEntry:
    availability = payload.get("availability")
    if availability not in ALLOWED_AVAILABILITY:
        raise ValueError(f"{name}: availability must be one of {sorted(ALLOWED_AVAILABILITY)}")
    max_target_lag_days = payload.get("max_target_lag_days")
    if max_target_lag_days is not None and int(max_target_lag_days) < 0:
        raise ValueError(f"{name}: max_target_lag_days must be >= 0")
    if pattern:
        re.compile(pattern)
    return FeatureAvailabilityEntry(
        name=name,
        availability=str(availability),
        source_model=payload.get("source_model"),
        timestamp_column=payload.get("timestamp_column"),
        source_cutoff_column=payload.get("source_cutoff_column"),
        plan_version_column=payload.get("plan_version_column"),
        materialization_column=payload.get("materialization_column"),
        max_target_lag_days=(int(max_target_lag_days) if max_target_lag_days is not None else None),
        pattern=pattern,
    )


def validate_feature_availability_registry(raw: dict[str, Any]) -> FeatureAvailabilityRegistry:
    """Validate and normalize a feature availability registry mapping."""
    feature_payloads = raw.get("features") or {}
    if not isinstance(feature_payloads, dict):
        raise ValueError("features must be a mapping of feature name to metadata")
    features: dict[str, FeatureAvailabilityEntry] = {}
    for feature_name, payload in feature_payloads.items():
        if not isinstance(payload, dict):
            raise ValueError(f"{feature_name}: feature metadata must be a mapping")
        features[str(feature_name)] = _entry_from_mapping(str(feature_name), payload)

    pattern_payloads = raw.get("patterns") or []
    if not isinstance(pattern_payloads, list):
        raise ValueError("patterns must be a list")
    patterns: list[FeatureAvailabilityEntry] = []
    for idx, payload in enumerate(pattern_payloads):
        if not isinstance(payload, dict):
            raise ValueError(f"patterns[{idx}] must be a mapping")
        pattern = payload.get("pattern")
        if not isinstance(pattern, str) or not pattern:
            raise ValueError(f"patterns[{idx}].pattern is required")
        patterns.append(_entry_from_mapping(f"patterns[{idx}]", payload, pattern=pattern))

    if not features and not patterns:
        raise ValueError("feature availability registry must contain features or patterns")
    return FeatureAvailabilityRegistry(
        raw={"features": feature_payloads, "patterns": pattern_payloads},
        features=features,
        patterns=tuple(patterns),
    )


def load_feature_availability_registry(
    path: str | Path | None = None,
) -> FeatureAvailabilityRegistry:
    """Load and validate the feature availability registry."""
    registry_path = Path(path) if path else DEFAULT_FEATURE_AVAILABILITY_PATH
    return validate_feature_availability_registry(_load_yaml(registry_path))


def registry_path_from_config(config: dict[str, Any]) -> str | Path | None:
    """Resolve registry path from model config, falling back to the default registry."""
    inputs = config.get("inputs") or {}
    outputs = config.get("outputs") or {}
    return (
        inputs.get("feature_availability_path")
        or outputs.get("feature_availability_path")
        or config.get("feature_availability_path")
    )


def validate_model_features_from_config(
    config: dict[str, Any],
    feature_names: Iterable[str],
    *,
    context: str,
) -> FeatureAvailabilityRegistry:
    """Validate concrete model features using the registry configured for a model job."""
    registry = load_feature_availability_registry(registry_path_from_config(config))
    registry.validate_features(feature_names, context=context)
    return registry


def validate_feature_cutoffs_from_config(
    config: dict[str, Any],
    df: pd.DataFrame,
    feature_names: Iterable[str],
    *,
    cutoff: Any | pd.Series,
    date_column: str | None = None,
    context: str,
) -> dict[str, Any]:
    """Validate feature registration and enforce source cutoffs for a model job."""
    registry = load_feature_availability_registry(registry_path_from_config(config))
    return registry.validate_frame_cutoffs(
        df,
        feature_names,
        cutoff=cutoff,
        date_column=date_column,
        context=context,
    )


def feature_cutoff_metadata_from_frame(
    df: pd.DataFrame,
    *,
    date_column: str | None = None,
    registry: FeatureAvailabilityRegistry | None = None,
    materialization_id: str | None = None,
) -> dict[str, Any]:
    """Build source cutoff metadata from an already-loaded feature frame."""
    payload: dict[str, Any] = {}
    if date_column and date_column in df.columns:
        max_date = pd.to_datetime(df[date_column], errors="coerce").max()
        if pd.notna(max_date):
            payload["data_cutoff"] = max_date.to_pydatetime().isoformat()
            payload["source_cutoff_json"] = {date_column: max_date.to_pydatetime().isoformat()}
    if registry:
        payload["feature_availability_hash"] = registry.hash
    if materialization_id:
        payload["feature_materialization_id"] = materialization_id
    return payload
