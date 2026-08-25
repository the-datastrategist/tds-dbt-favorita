{% docs spec_forecast_contract_and_output %}

# SPEC: Forecast contract and canonical output

**Status:** Shipped
**Roadmap reference:** [Specs overview](README.md) — P0 "Introduce a forecast contract"

---

## Summary

The current Vertex prediction table is model-run oriented: it records predictions, metadata, and optional actuals after a configured job runs. A demand forecasting platform needs a stronger contract that describes the forecasting problem before any model is trained or scored, and a canonical output table that separates statistical forecasts, planner changes, approvals, and published versions.

This spec introduces `docs/forecast_contract.md`, a validated YAML contract, and canonical BigQuery tables for versioned multi-horizon forecast output.

## Goals

- Define one forecast contract shape for target, grain, schedule, horizons, quantiles, eligibility, covariate availability, hierarchy, and reconciliation.
- Validate forecast contracts before training, scoring, backtesting, or publishing.
- Add a canonical output schema keyed by `forecast_run_id`, `forecast_origin`, `series_key`,
  `target_timestamp`, and `horizon`.
- Persist provenance on every forecast row: model version, feature version, code SHA, data cutoff, config hash, and status.
- Support separate values for statistical forecast, planner override, approved forecast, and published forecast.

## Non-goals

- Building planner UI workflows. The schema must support them, but workflow implementation belongs in [forecast operations](forecast_operations.md).
- Implementing reconciliation algorithms. The contract records the reconciliation policy; algorithms belong in [hierarchical reconciliation](hierarchical_reconciliation.md).
- Replacing existing model prediction tables immediately. The first implementation may write both schemas until downstream docs and marts migrate.

## Design

### 1. Forecast contract document

Add `docs/forecast_contract.md` with reader-facing documentation and examples. It should explain required fields, defaults, validation rules, and how the contract maps to dbt, Vertex, and publishing outputs.

Example:

```yaml
forecast:
  name: store_product_daily
  target: demand_units
  target_unit: units
  dimensions: [store_id, product_id]
  frequency: day
  timezone: America/Guayaquil
  issue_schedule: "0 6 * * *"
  horizons: [1, 2, 3, 4, 5, 6, 7, 14, 28]
  quantiles: [0.1, 0.5, 0.9]
  training_window_days: 730
  known_future_features: [promotion, holiday, planned_price]
  observed_features: [sales, transactions, inventory_on_hand]
  hierarchy: [company, store, product_family, product]
  reconciliation_policy: bottom_up
```

### 2. Contract schema and loader

Add a Python module under `forecasting_core/contracts/` or, before modularization, `vertex/config/forecast_contract.py`.

Responsibilities:

- Load YAML from a path or named config.
- Validate required fields and allowed values.
- Normalize horizons and quantiles.
- Produce a stable `forecast_contract_hash`.
- Expose helper methods used by training, scoring, backtesting, and publishing.

Validation should reject:

- Empty horizons.
- Quantiles outside `(0, 1)`.
- Observed features listed as known-future features.
- Missing timezone or frequency.
- Reconciliation policy without hierarchy when policy is not `none`.

### 3. Canonical tables

Add DDL for forecast contract and output tables, either in `vertex/ddl/vertex_bq_tables.sql` or a new `forecasting_core/ddl/forecast_tables.sql`.

Minimum tables:

| Table | Purpose |
|-------|---------|
| `forecast_contracts` | Registered contract versions and config hashes |
| `forecast_runs` | One row per scoring/backtest/publication run |
| `forecast_outputs` | One row per series, origin, target timestamp, horizon, and forecast version |
| `forecast_status_history` | Audit trail for draft, approved, published, superseded, failed |

Minimum `forecast_outputs` columns:

```text
forecast_run_id
forecast_contract_name
forecast_contract_hash
forecast_origin
series_key
entity_key_json
target_timestamp
target_date
horizon
grain
prediction_p10
prediction_p50
prediction_p90
statistical_forecast
planner_override
approved_forecast
published_forecast
forecast_status
model_run_id
model_id
feature_version
code_sha
data_cutoff
created_at
```

Rows eligible for scheduled publication additionally require:

```text
forecast_strategy
fallback_reason
confidence_flag
calibration_method
calibration_run_id
hierarchy_version
reconciliation_method
reconciliation_run_id
publication_version
prefect_flow_run_id
```

`fallback_reason` may be null when the primary strategy succeeds. Reconciliation identifiers may
be null only when the validated contract declares no hierarchy and records method `none`. The
publication writer rejects rows missing required stage lineage, configured horizons or quantiles,
or ordered quantiles. The complete stage order, pinned run identity, visibility boundary, quality
gates, failure behavior, and idempotency rules are defined by the authoritative
[scheduled forecast publication pipeline](scheduled_forecast_publication_pipeline.md).

Use a normalized quantile child table if configurable quantiles become too wide for stable table evolution.

### 4. dbt staging and marts

Add dbt source declarations and staging models:

- `stg_forecast_contracts`
- `stg_forecast_runs`
- `stg_forecast_outputs`
- `stg_forecast_status_history`

Add tests:

- `not_null` on run IDs, origin, series key, target timestamp, horizon, status.
- accepted values for status.
- uniqueness on `(forecast_run_id, series_key, target_timestamp, horizon)` for draft output rows.
- one-to-one consistency between `series_key` and `entity_key_json` within a dataset contract.
- no negative horizons.

### 5. Compatibility with existing Vertex predictions

Initial implementation can adapt the existing model prediction fact table into `forecast_outputs` for the active project config. The mapping should use:

| Existing | Canonical |
|----------|-----------|
| `predict_run_id` | `forecast_run_id` |
| `target_timestamp` | `target_timestamp` |
| `forecast_date` / `date` | compatibility `target_date`, converted to `target_timestamp` when canonical time is absent |
| `series_key` | `series_key` |
| dimension columns | compatibility input used to derive `series_key` and `entity_key_json` when canonical identity is absent |
| model prediction | `statistical_forecast`, `prediction_p50` |
| `actual` | retained in evaluation tables, not canonical output |
| `model_run_id`, `model_id` | same |

## Implementation plan

1. Add reader-facing `docs/forecast_contract.md`.
2. Add contract loader and validation tests.
3. Extend DDL with contract/run/output/status tables.
4. Add dbt sources, staging models, schema docs, and tests.
5. Add a Vertex prediction writer path that emits canonical forecast output for one default config.
6. Update `README.md`, `docs/reference_architecture.md`, and `docs/overview.md` to call this a forecast contract.

## Testing & validation

- Unit tests for contract validation and hash stability.
- DDL applicator test or dry-run validation for new tables.
- dbt parse/compile/docs generation.
- A local or GCP smoke test that writes a 7-day forecast and confirms every row has origin, target date, horizon, model version, feature version, code SHA, and data cutoff.

## Implementation and acceptance

The contract loader, canonical BigQuery tables, model-writer integration, publication lifecycle,
dbt staging, and validation tests are implemented. New canonical rows carry
`contract_enforced = true`; historical append-only rows remain available through staging as
`contract_enforced = false`, which provides an explicit migration boundary without rewriting
history.

The portability migration now carries `series_key`, `entity_key_json`, and `target_timestamp`
through scoring, publication, reconciliation, retrieval, realized calibration, and FVA. Daily
`target_date` and retail dimension fields remain compatibility projections. Existing deployments
must apply the idempotent BigQuery DDL before rebuilding the updated dbt staging and monitoring
models.

Live GCP acceptance passed on 2026-07-18 using 51 real horizon-7 XGBoost predictions. The run
persisted 51 canonical outputs, automatically approved and published all 51, and reported zero
horizon, quantile-order, provenance, or delivery-status violations. The complete forecast staging
suite subsequently passed 107 data tests. See
[forecast contract acceptance evidence](../acceptance/forecast_contract_2026-07-18.md).

## Acceptance criteria

- A named forecast contract can be validated from YAML.
- A multi-horizon forecast run records one canonical output row per series/target timestamp/horizon.
- Every canonical forecast row has provenance and lifecycle status.
- Every published row has routing, calibration, reconciliation, orchestration, and publication
  version lineage applicable to its contract.
- Existing model predictions can be queried through `stg_forecast_outputs`.

## Shipped evidence

This contract is shipped. Live GCP acceptance produced one provenance-complete, contract-valid
54-row canonical draft and an identical retry created no duplicate run, output, stage, validation,
or status records. The accepted run, lineage identifiers, results, and reproducible SQL are
recorded in [scheduled forecast publication acceptance](../acceptance/scheduled_forecast_publication_2026-08-05.md).

## Related documents

- [Specs index](README.md)
- [Forecasting methods](forecasting_methods.md)
- [Backtesting and model lifecycle](backtesting_and_model_lifecycle.md)
- [Forecast operations](forecast_operations.md)
- [Scheduled forecast publication pipeline](scheduled_forecast_publication_pipeline.md)
- [Integration contracts](integration_contracts.md)

{% enddocs %}
