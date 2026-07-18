# Forecast Contract

A forecast contract defines the forecasting problem before any model is trained, scored, approved, or published. It is the portability boundary for this GCP demand forecasting platform: each project owns its dbt feature models, but every project should express its target, grain, horizon, covariates, hierarchy, and output semantics through a validated contract.

## Required Fields

```yaml
forecast:
  name: store_daily_demand
  target: demand_units
  target_unit: units
  dimensions: [store_id]
  frequency: day
  timezone: America/New_York
  issue_schedule: "0 6 * * *"
  horizons: [1, 2, 3, 4, 5, 6, 7]
  quantiles: [0.1, 0.5, 0.9]
  training_window_days: 730
  known_future_features: [promotion, holiday]
  observed_features: [sales, transactions]
  hierarchy: [company, store]
  reconciliation_policy: none
  demand_policy: observed_sales_only
```

## Semantics

| Field | Meaning |
|-------|---------|
| `name` | Stable contract name used in forecast output rows. |
| `target` / `target_unit` | Business metric being forecasted and its unit. |
| `dimensions` | Entity keys that define one forecasted item at the contract grain. |
| `frequency` | Time grain, currently `day`. |
| `timezone` | Business timezone for forecast origins and publication SLAs. |
| `issue_schedule` | Cron expression for expected forecast issue time. |
| `horizons` | Required forecast horizons. Outputs and metrics must be horizon-aware. |
| `quantiles` | Requested probabilistic outputs. P50 maps to the canonical statistical forecast. |
| `training_window_days` | Default historical training window. |
| `known_future_features` | Covariates available at forecast origin for future target dates. |
| `observed_features` | Covariates only available after observation and therefore subject to cutoffs/lags. |
| `hierarchy` | Business hierarchy levels used by reconciliation and reporting. |
| `reconciliation_policy` | Reconciliation method. Use `none` for a first run; enable a configured hierarchy method only after its scheduled-path validation is accepted. |
| `demand_policy` | Whether the target represents observed sales, adjusted demand, or another policy. |

## Canonical Output

Prediction jobs may continue writing model-oriented prediction tables during migration, but they should also write canonical forecast rows when `outputs.forecast_output_table` is configured.

Canonical rows include:

- `forecast_run_id`
- `forecast_contract_name`
- `forecast_contract_hash`
- `forecast_origin`
- `target_date`
- `horizon`
- entity keys and `entity_key_json`
- `prediction_p10`, `prediction_p50`, `prediction_p90`
- `statistical_forecast`
- `planner_override`, `approved_forecast`, `published_forecast`
- `forecast_status`
- model, feature, code, artifact, and data-cutoff provenance

Initial prediction jobs write `forecast_status = 'draft'`. Approval, publication, supersession, and rollback are handled by the forecast operations layer.

## Feature Availability

Forecast contract feature declarations are validated against `vertex/config/feature_availability.yaml`. `known_future_features` must resolve to features classified as `known_future`, `forecasted_external`, `planned_revisable`, or `static_master_data`, and future-known or planned features must include cutoff/version metadata. `observed_features` must resolve to observed feature classes.

Concrete model input features are validated after the training or scoring feature matrix is built. Features classified as `observed_after_period` are rejected as model inputs, which prevents target-derived future labels from leaking into training, optimization, or prediction.

## Project Adaptation

New projects should:

1. Create or update `vertex/config/forecast_contract.yaml`.
2. Create or update `vertex/config/feature_availability.yaml`.
3. Build dbt staging and feature models that match the contract's dimensions, target, covariates, and horizons.
4. Point `model_config.yaml` training and prediction SQL at those dbt models.
5. Keep `outputs.forecast_output_table` enabled so every prediction has canonical forecast output.
