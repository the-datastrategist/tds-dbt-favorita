# Extension guide

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
