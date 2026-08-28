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


def load_model_provider(config: dict[str, Any], *, model_type: str, step: str) -> Any:
    """Resolve a configured model provider, or the compatible built-in provider.

    A model extension spec may set ``model_type`` to scope it to one configured model
    type. More than one matching provider is rejected so production dispatch is explicit.
    """
    from vertex.extensions.builtins import BUILTIN_MODEL_PROVIDERS
    from vertex.extensions.contracts import ModelProvider

    matches: list[Any] = []
    for spec in (config.get("extensions") or {}).get("models", []):
        if not isinstance(spec, dict):
            raise ExtensionLoadError("model extension entries must be mappings")
        scoped_type = spec.get("model_type")
        if scoped_type is not None and scoped_type != model_type:
            continue
        provider = load_extension(
            str(spec.get("provider", "")),
            ModelProvider,
            required_capabilities=frozenset({f"model.{step}"}),
        )
        matches.append(provider)
    if len(matches) > 1:
        raise ExtensionLoadError(f"multiple model providers match model_type {model_type!r}")
    if matches:
        return matches[0]
    provider_type = BUILTIN_MODEL_PROVIDERS.get(model_type)
    if provider_type is None:
        raise ExtensionLoadError(f"no built-in provider for model_type {model_type!r}")
    provider = provider_type()
    if f"model.{step}" not in provider.metadata.capabilities:
        raise ExtensionLoadError(f"provider {provider.metadata.name!r} does not support {step!r}")
    return provider


def load_optional_providers(config: dict[str, Any]) -> dict[str, list[Any]]:
    """Load configured non-model providers before a production job mutates state.

    Model providers are selected per step by :func:`load_model_provider`; these
    optional categories are loaded at job startup so a bad import, API version, or
    declared capability fails before training or scoring begins.  The returned
    instances are also available to orchestration callers that own the relevant
    dataset, metric, routing, or publication operation.
    """
    from vertex.extensions.contracts import (
        DatasetAdapter,
        ForecastPublisher,
        MetricProvider,
        RoutingStrategy,
    )

    extensions = dict(config.get("extensions") or {})
    extensions.pop("models", None)
    return load_extension_config(
        {"extensions": extensions},
        {
            "datasets": DatasetAdapter,
            "metrics": MetricProvider,
            "routing": RoutingStrategy,
            "publishers": ForecastPublisher,
        },
    )
