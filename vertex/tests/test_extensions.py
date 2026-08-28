"""Contract and discovery tests for external extension providers."""

import pytest

from vertex.extensions.builtins import XGBoostProvider
from vertex.extensions.contracts import (
    DatasetAdapter,
    DatasetRequest,
    DatasetResolution,
    ExtensionMetadata,
    ForecastPublisher,
    MetricProvider,
    MetricRequest,
    MetricResult,
    ModelProvider,
    PublicationReceipt,
    PublicationRequest,
    RoutingDecision,
    RoutingRequest,
    RoutingStrategy,
)
from vertex.extensions.loader import ExtensionLoadError, load_extension, load_extension_config
from vertex.extensions.testing import assert_provider_contract


class ToyDatasetAdapter:
    metadata = ExtensionMetadata("toy-dataset", capabilities=frozenset({"dataset.resolve"}))

    def resolve(self, request: DatasetRequest) -> DatasetResolution:
        return DatasetResolution(request.relation, {"series": "series_key"})


class ToyMetric:
    metadata = ExtensionMetadata("toy-mae", capabilities=frozenset({"metric.evaluate"}))
    required_columns = frozenset({"actual", "prediction"})
    direction = "minimize"

    def evaluate(self, request: MetricRequest) -> MetricResult:
        return MetricResult("toy-mae", 0.0, self.direction)


class ToyRoutingStrategy:
    metadata = ExtensionMetadata("toy-routing", capabilities=frozenset({"routing.select"}))

    def select(self, request: RoutingRequest) -> RoutingDecision:
        return RoutingDecision("global_model", "toy decision", 1.0)


class ToyPublisher:
    metadata = ExtensionMetadata("toy-publisher", capabilities=frozenset({"publisher.publish"}))

    def publish(self, request: PublicationRequest) -> PublicationReceipt:
        return PublicationReceipt("memory", request.idempotency_key, len(request.rows))


@pytest.mark.unit
def test_loads_external_providers_without_central_registry_changes() -> None:
    providers = load_extension_config(
        {
            "extensions": {
                "datasets": [
                    {
                        "provider": "vertex.tests.test_extensions:ToyDatasetAdapter",
                        "required_capabilities": ["dataset.resolve"],
                    }
                ],
                "metrics": [{"provider": "vertex.tests.test_extensions:ToyMetric"}],
                "routing": [{"provider": "vertex.tests.test_extensions:ToyRoutingStrategy"}],
                "publishers": [{"provider": "vertex.tests.test_extensions:ToyPublisher"}],
            }
        },
        {
            "datasets": DatasetAdapter,
            "metrics": MetricProvider,
            "routing": RoutingStrategy,
            "publishers": ForecastPublisher,
        },
    )

    assert providers["datasets"][0].metadata.name == "toy-dataset"
    assert providers["metrics"][0].metadata.name == "toy-mae"
    assert providers["routing"][0].metadata.name == "toy-routing"
    assert providers["publishers"][0].metadata.name == "toy-publisher"


@pytest.mark.unit
def test_builtin_model_provider_satisfies_public_contract() -> None:
    provider = load_extension(
        "vertex.extensions.builtins:XGBoostProvider",
        ModelProvider,
        required_capabilities=frozenset({"model.train", "model.predict"}),
    )

    assert isinstance(provider, XGBoostProvider)
    assert_provider_contract(provider, capabilities=frozenset({"model.optimize"}))


@pytest.mark.unit
def test_rejects_incompatible_or_missing_extension() -> None:
    with pytest.raises(ExtensionLoadError, match="module:Class"):
        load_extension("invalid", MetricProvider)
    with pytest.raises(ExtensionLoadError, match="cannot load"):
        load_extension("vertex.tests.test_extensions:Missing", MetricProvider)
