# Extension guide

The stable in-process API lives in `vertex.extensions` and is versioned independently from model
configuration. Providers are explicit `module:Class` imports; startup validation checks the
runtime interface, API version, stable provider name, and required capabilities before execution.
Import-path loading never scans the environment or mutates the central model registry.

```yaml
extensions:
  models:
    - type: lightgbm
      provider: client_forecasting.models:LightGBMProvider
      required_capabilities: [model.train, model.predict]
```

Provider contracts are `ModelProvider`, `DatasetAdapter`, `MetricProvider`, `RoutingStrategy`, and
`ForecastPublisher` in `vertex/extensions/contracts.py`. Requests and results are frozen typed
dataclasses. API version `1` follows semantic compatibility: fields and capabilities may be added
compatibly; removals, renamed meanings, or changed method signatures require a new API version and
a documented deprecation window.

Load a provider explicitly:

```python
from vertex.extensions.contracts import ModelProvider
from vertex.extensions.loader import load_extension

provider = load_extension(
    "client_forecasting.models:LightGBMProvider",
    ModelProvider,
    required_capabilities=frozenset({"model.predict"}),
)
```

Extension failures use `ExtensionLoadError` for malformed paths, import/constructor errors,
interface mismatches, incompatible API versions, and missing capabilities. Provider execution
errors remain provider-specific and must not be silently converted into successful results.

External packages can reuse `assert_provider_contract` from `vertex.extensions.testing` in their
own test suite. The built-in XGBoost, random-forest, ARIMA, SARIMA, and Prophet compatibility
providers demonstrate the model interface without changing existing job behavior.

## Model families

Implement the existing train/predict artifact contract, register the family in
`vertex/models/registry.py`, persist comparable evaluation metadata, add configuration validation,
and prove rolling-origin and forecast-output tests. Model code must not bypass point-in-time feature
or publication contracts.

## dbt project implementations

Map source-specific fields into canonical demand, eligibility, feature, and forecast grains. Keep
business semantics in the project layer, preserve generic column contracts, add schema tests, and
record controlled live acceptance. Do not embed Favorita table names in generic Python modules.

## Forecast destinations

Consume immutable publication events or stable views. A destination adapter must be idempotent,
record delivery attempts and terminal status, retain contract/run/version identifiers, and avoid
changing canonical forecasts. Signed webhooks and GCS exports are reference implementations.

Generic contract and evaluation utilities will move first toward `forecasting_core/`; project
examples and GCP deployment code remain compatible through documented shims during modularization.
