"""Built-in adapters that expose existing model runners through the extension API."""

from __future__ import annotations

from typing import Any, Mapping

from vertex.config.load_config import validate_config_for_step
from vertex.extensions.contracts import ExtensionMetadata, ModelRequest, ProviderResult
from vertex.models.registry import get_runner


class RegistryModelProvider:
    """Compatibility provider for one model family in the existing runner registry."""

    model_type = ""
    supported_steps = frozenset({"train", "predict", "optimize"})

    @property
    def metadata(self) -> ExtensionMetadata:
        return ExtensionMetadata(
            name=self.model_type,
            capabilities=frozenset(f"model.{step}" for step in self.supported_steps),
        )

    def validate(self, config: Mapping[str, Any]) -> None:
        validate_config_for_step(dict(config))

    def _execute(self, step: str, request: ModelRequest) -> ProviderResult:
        config = dict(request.config)
        self.validate(config)
        result = get_runner(self.model_type, step)(config)
        if not isinstance(result, dict):
            raise TypeError("model runner must return a result mapping")
        return ProviderResult(result)

    def train(self, request: ModelRequest) -> ProviderResult:
        return self._execute("train", request)

    def predict(self, request: ModelRequest) -> ProviderResult:
        return self._execute("predict", request)

    def optimize(self, request: ModelRequest) -> ProviderResult:
        return self._execute("optimize", request)


class XGBoostProvider(RegistryModelProvider):
    model_type = "xgboost"


class RandomForestProvider(RegistryModelProvider):
    model_type = "random_forest"


class ArimaProvider(RegistryModelProvider):
    model_type = "arima"


class SarimaProvider(RegistryModelProvider):
    model_type = "sarima"


class ProphetProvider(RegistryModelProvider):
    model_type = "prophet"
