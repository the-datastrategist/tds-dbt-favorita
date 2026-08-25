"""Hierarchy configuration loader and validation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml

from vertex.utils.data_utils import get_hash

VALID_METHODS = frozenset({"bottom_up", "top_down", "middle_out", "mint"})
SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class HierarchyConfig:
    raw: dict[str, Any]

    @property
    def spec(self) -> dict[str, Any]:
        return cast(dict[str, Any], self.raw["hierarchy"])

    @property
    def name(self) -> str:
        return str(self.spec["name"])

    @property
    def version(self) -> str:
        return str(self.spec.get("version", self.hash))

    @property
    def hash(self) -> str:
        return get_hash(self.raw)

    @property
    def levels(self) -> list[dict[str, Any]]:
        return list(self.spec["levels"])

    @property
    def source(self) -> dict[str, str]:
        return cast(dict[str, str], self.spec["source"])

    @property
    def method(self) -> str:
        return str(self.spec["reconciliation"]["method"])

    @property
    def tolerance_abs(self) -> float:
        return float(self.spec["reconciliation"].get("tolerance_abs", 0.01))

    @property
    def middle_level(self) -> str | None:
        value = self.spec["reconciliation"].get("middle_level")
        return str(value) if value is not None else None


def validate_hierarchy_config(raw: dict[str, Any]) -> HierarchyConfig:
    spec = raw.get("hierarchy")
    if not isinstance(spec, dict):
        raise ValueError("hierarchy config must contain a hierarchy mapping")
    if not isinstance(spec.get("name"), str) or not spec["name"]:
        raise ValueError("hierarchy.name is required")
    levels = spec.get("levels")
    if not isinstance(levels, list) or len(levels) < 2:
        raise ValueError("hierarchy.levels must contain at least two levels")
    names: list[str] = []
    previous_keys: set[str] = set()
    for position, level in enumerate(levels):
        if not isinstance(level, dict) or not isinstance(level.get("name"), str):
            raise ValueError("every hierarchy level must have a name")
        name = level["name"]
        keys = level.get("keys")
        if not isinstance(keys, list) or not all(isinstance(key, str) and key for key in keys):
            raise ValueError(f"hierarchy level {name!r} keys must be a list of strings")
        if len(set(keys)) != len(keys):
            raise ValueError(f"hierarchy level {name!r} contains duplicate keys")
        if position and not previous_keys.issubset(keys):
            raise ValueError("hierarchy level keys must retain all parent-level keys")
        names.append(name)
        previous_keys = set(keys)
    if len(set(names)) != len(names):
        raise ValueError("hierarchy level names must be unique")

    source = spec.get("source")
    if not isinstance(source, dict):
        raise ValueError("hierarchy.source is required")
    for field in ("relation", "entity_key_json_column", "effective_from"):
        if not isinstance(source.get(field), str) or not source[field]:
            raise ValueError(f"hierarchy.source.{field} is required")
    if not SAFE_IDENTIFIER.fullmatch(source["relation"]):
        raise ValueError("hierarchy.source.relation must be an unqualified relation name")
    if not SAFE_IDENTIFIER.fullmatch(source["entity_key_json_column"]):
        raise ValueError("hierarchy.source.entity_key_json_column must be a safe identifier")

    reconciliation = spec.get("reconciliation")
    if not isinstance(reconciliation, dict):
        raise ValueError("hierarchy.reconciliation is required")
    method = reconciliation.get("method")
    if method not in VALID_METHODS:
        raise ValueError(f"hierarchy reconciliation method must be one of {sorted(VALID_METHODS)}")
    tolerance = reconciliation.get("tolerance_abs", 0.01)
    if not isinstance(tolerance, (int, float)) or tolerance < 0:
        raise ValueError("hierarchy.reconciliation.tolerance_abs must be non-negative")
    middle_level = reconciliation.get("middle_level")
    if method == "middle_out" and middle_level not in names[1:-1]:
        raise ValueError("middle_out requires a non-terminal middle_level")
    return HierarchyConfig({"hierarchy": spec})


def load_hierarchy_config(path: str | Path) -> HierarchyConfig:
    config_path = Path(path)
    if not config_path.is_file():
        raise FileNotFoundError(f"Hierarchy config not found: {config_path}")
    with config_path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Expected mapping at root of {config_path}")
    return validate_hierarchy_config(raw)
