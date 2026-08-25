"""Versioned request, result, and provider protocols for extensions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, runtime_checkable

EXTENSION_API_VERSION = "1"


@dataclass(frozen=True)
class ExtensionMetadata:
    name: str
    api_version: str = EXTENSION_API_VERSION
    capabilities: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class ModelRequest:
    config: Mapping[str, Any]


@dataclass(frozen=True)
class ProviderResult:
    values: Mapping[str, Any]


@dataclass(frozen=True)
class DatasetRequest:
    relation: str
    purpose: str
    options: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DatasetResolution:
    relation: str
    roles: Mapping[str, str]


@dataclass(frozen=True)
class MetricRequest:
    rows: Any
    options: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MetricResult:
    name: str
    value: float
    direction: str


@dataclass(frozen=True)
class RoutingRequest:
    candidates: Any
    context: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RoutingDecision:
    strategy: str
    reason: str
    confidence: float | None = None


@dataclass(frozen=True)
class PublicationRequest:
    rows: Any
    forecast_run_id: str
    publication_version: int
    idempotency_key: str


@dataclass(frozen=True)
class PublicationReceipt:
    destination: str
    reference: str
    row_count: int


@runtime_checkable
class ModelProvider(Protocol):
    metadata: ExtensionMetadata
    supported_steps: frozenset[str]

    def validate(self, config: Mapping[str, Any]) -> None: ...

    def train(self, request: ModelRequest) -> ProviderResult: ...

    def predict(self, request: ModelRequest) -> ProviderResult: ...

    def optimize(self, request: ModelRequest) -> ProviderResult: ...


@runtime_checkable
class DatasetAdapter(Protocol):
    metadata: ExtensionMetadata

    def resolve(self, request: DatasetRequest) -> DatasetResolution: ...


@runtime_checkable
class MetricProvider(Protocol):
    metadata: ExtensionMetadata
    required_columns: frozenset[str]
    direction: str

    def evaluate(self, request: MetricRequest) -> MetricResult: ...


@runtime_checkable
class RoutingStrategy(Protocol):
    metadata: ExtensionMetadata

    def select(self, request: RoutingRequest) -> RoutingDecision: ...


@runtime_checkable
class ForecastPublisher(Protocol):
    metadata: ExtensionMetadata

    def publish(self, request: PublicationRequest) -> PublicationReceipt: ...
