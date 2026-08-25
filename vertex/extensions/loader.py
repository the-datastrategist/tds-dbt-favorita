"""Explicit, validated import-path loading for configured extensions."""

from __future__ import annotations

import importlib
from typing import Any

from vertex.extensions.contracts import EXTENSION_API_VERSION, ExtensionMetadata

class ExtensionLoadError(ValueError):
    """An extension cannot be imported or does not satisfy its declared contract."""


def load_extension(
    import_path: str,
    interface: type[Any],
    *,
    required_capabilities: frozenset[str] = frozenset(),
) -> Any:
    """Instantiate and validate `module:Class` against a runtime protocol."""
    if import_path.count(":") != 1:
        raise ExtensionLoadError("extension path must use module:Class syntax")
    module_name, attribute_name = import_path.split(":", 1)
    if not module_name or not attribute_name or attribute_name.startswith("_"):
        raise ExtensionLoadError("extension path must name a public class")
    try:
        extension_type = getattr(importlib.import_module(module_name), attribute_name)
        extension = extension_type()
    except (ImportError, AttributeError, TypeError) as exc:
        raise ExtensionLoadError(f"cannot load extension {import_path!r}: {exc}") from exc
    if not isinstance(extension, interface):
        raise ExtensionLoadError(
            f"extension {import_path!r} does not implement {interface.__name__}"
        )
    metadata = getattr(extension, "metadata", None)
    if not isinstance(metadata, ExtensionMetadata) or not metadata.name:
        raise ExtensionLoadError("extension metadata with a stable name is required")
    if metadata.api_version != EXTENSION_API_VERSION:
        raise ExtensionLoadError(
            f"extension API {metadata.api_version!r} is incompatible with "
            f"{EXTENSION_API_VERSION!r}"
        )
    missing = required_capabilities.difference(metadata.capabilities)
    if missing:
        raise ExtensionLoadError(f"extension is missing capabilities: {sorted(missing)}")
    return extension


def load_extension_config(
    config: dict[str, Any], interfaces: dict[str, type[Any]]
) -> dict[str, list[Any]]:
    """Load categorized extension specs from an `extensions` configuration mapping."""
    result: dict[str, list[Any]] = {}
    for category, specs in (config.get("extensions") or {}).items():
        if category not in interfaces:
            raise ExtensionLoadError(f"unknown extension category {category!r}")
        if not isinstance(specs, list):
            raise ExtensionLoadError(f"extension category {category!r} must be a list")
        result[category] = []
        for spec in specs:
            if not isinstance(spec, dict) or not isinstance(spec.get("provider"), str):
                raise ExtensionLoadError(f"extension category {category!r} has an invalid spec")
            required = frozenset(spec.get("required_capabilities") or [])
            result[category].append(
                load_extension(
                    spec["provider"], interfaces[category], required_capabilities=required
                )
            )
    return result
