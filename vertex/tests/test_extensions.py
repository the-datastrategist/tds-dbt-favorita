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
    ModelRequest,
    ProviderResult,
    PublicationReceipt,
    PublicationRequest,
    RoutingDecision,
    RoutingRequest,
    RoutingStrategy,
)
from vertex.extensions.loader import (
    ExtensionLoadError,
    load_extension,
    load_extension_config,
    load_model_provider,
    load_optional_providers,
)
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


class ToyModelProvider:
    metadata = ExtensionMetadata("toy-model", capabilities=frozenset({"model.train"}))
    supported_steps = frozenset({"train"})

    def validate(self, config):
        return None

    def train(self, request: ModelRequest) -> ProviderResult:
        return ProviderResult({"provider": "toy"})

    def predict(self, request: ModelRequest) -> ProviderResult:
        raise NotImplementedError

    def optimize(self, request: ModelRequest) -> ProviderResult:
        raise NotImplementedError


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
def test_production_model_provider_resolution_is_explicit_and_uses_builtin_fallback() -> None:
    provider = load_model_provider(
        {
            "extensions": {
                "models": [
                    {
                        "model_type": "toy",
                        "provider": "vertex.tests.test_extensions:ToyModelProvider",
                    }
                ]
            }
        },
        model_type="toy",
        step="train",
    )
    assert provider.metadata.name == "toy-model"
    assert load_model_provider({}, model_type="xgboost", step="predict").metadata.name == "xgboost"


@pytest.mark.unit
def test_production_startup_loads_configured_optional_providers() -> None:
    providers = load_optional_providers(
        {
            "extensions": {
                "datasets": [{"provider": "vertex.tests.test_extensions:ToyDatasetAdapter"}],
                "publishers": [{"provider": "vertex.tests.test_extensions:ToyPublisher"}],
            }
        }
    )
    assert [item.metadata.name for item in providers["datasets"]] == ["toy-dataset"]
    assert [item.metadata.name for item in providers["publishers"]] == ["toy-publisher"]


@pytest.mark.unit
def test_rejects_incompatible_or_missing_extension() -> None:
    with pytest.raises(ExtensionLoadError, match="module:Class"):
        load_extension("invalid", MetricProvider)
    with pytest.raises(ExtensionLoadError, match="cannot load"):
        load_extension("vertex.tests.test_extensions:Missing", MetricProvider)
