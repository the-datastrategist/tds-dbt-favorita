"""Reusable provider conformance assertions for extension authors."""

from __future__ import annotations

from typing import Any

from vertex.extensions.contracts import EXTENSION_API_VERSION, ExtensionMetadata


def assert_provider_contract(provider: Any, *, capabilities: frozenset[str] = frozenset()) -> None:
    """Assert common metadata and capability invariants for every provider type."""
    metadata = getattr(provider, "metadata", None)
    assert isinstance(metadata, ExtensionMetadata)
    assert metadata.name.strip()
    assert metadata.api_version == EXTENSION_API_VERSION
    assert capabilities.issubset(metadata.capabilities)
