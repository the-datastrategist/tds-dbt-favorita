{% docs spec_point_in_time_feature_availability %}

# SPEC: Point-in-time feature availability

**Status:** In progress
**Roadmap reference:** [Specs overview](README.md) — P0 "Enforce point-in-time feature correctness"

---

## Summary

Demand forecasting only works as a decision system when features reflect what was knowable at the forecast origin. The current dbt feature layer is well documented, but feature availability is not represented as a first-class contract. This spec adds a feature-availability registry, leakage tests, and data-cutoff recording for every forecast run.

## Goals

- Classify each feature as observed-after-target, known-in-advance, forecasted external input, or planned-but-revisable.
- Require backtests and production scoring to use the same information set.
- Record source data cutoff timestamps on every forecast run.
- Add automated leakage tests for common violations.
- Document feature availability in `docs/forecast_contract.md` and dbt docs.

## Non-goals

- Building a full feature store. This spec adds registry and tests around dbt/BigQuery feature tables.
- Forecasting external covariates such as weather or price. Those are represented as feature types; model implementations come later.

## Design

### 1. Feature availability registry

Add a registry file, for example `dbt/models/features/feature_availability.yml` or `forecasting_core/features/availability.yml`.

Example:

```yaml
features:
  promotion:
    availability: known_future
    source_model: stg_sales_fct
    timestamp_column: promotion_plan_updated_at
  sales_store_l7d:
    availability: observed_lagged
    source_model: int_sales_store_daily
    max_target_lag_days: 1
  transactions:
    availability: observed_after_period
    source_model: stg_transactions
  planned_price:
    availability: planned_revisable
    source_model: stg_price_plan
```

Allowed availability values:

- `known_future`
- `observed_lagged`
- `observed_after_period`
- `forecasted_external`
- `planned_revisable`
- `static_master_data`

### 2. Forecast contract integration

Forecast contracts must reference feature groups or explicit features. Validation should fail if:

- a feature is used but not registered
- an observed-after-period feature is used for a future horizon without an approved lag
- a known-future feature has no plan/source cutoff metadata

### 3. Leakage tests

Add dbt singular tests or Python checks:

- no feature timestamp later than forecast origin, except approved known-future features
- target-derived lags use only dates before the origin/target as configured
- forecasted external inputs are versioned by origin
- planned-but-revisable inputs record the plan version used

### 4. Forecast run cutoffs

Extend `forecast_runs` from [forecast contract and canonical output](forecast_contract_and_output.md) with:

```text
data_cutoff
source_cutoff_json
feature_availability_hash
feature_materialization_id
```

### 5. dbt documentation

Add registry-driven docs to staging/intermediate schema descriptions where practical. At minimum, add a page `docs/feature_availability.md` documenting the feature classes and how to add a feature safely.

### 6. Scheduled publication integration

The publication pipeline freezes `source_cutoff_json`, `feature_availability_hash`,
`feature_materialization_id`, and the eligible entity snapshot before scoring. These values are
part of the logical run identity, so a changed cutoff or rematerialized feature set creates a new
run rather than mutating an in-flight forecast. Any source timestamp beyond its allowed cutoff is
a blocking publication-gate failure. Locking, retries, and atomic draft visibility are defined by
the [scheduled forecast publication pipeline](scheduled_forecast_publication_pipeline.md).

## Implementation plan

1. Add registry YAML and loader.
2. Register existing `int_sales_*` features at a coarse first-pass level.
3. Add contract validation against the registry.
4. Add leakage tests for lag and future-date violations.
5. Record source cutoff JSON in forecast runs.
6. Update backtest runner to use origin-specific cutoffs.

## Testing & validation

- Unit tests for registry validation.
- Fixture test where a target-leaking feature is rejected.
- dbt test that fails when feature dates exceed allowed cutoffs.
- Backtest smoke test proving each origin records distinct source cutoffs.

## Acceptance criteria

- Every feature used by the default forecast contract is registered.
- Backtests and production scoring both record feature availability hash and source cutoffs.
- At least one automated test catches a deliberately leaking feature.

## Related documents

- [Forecast contract and canonical output](forecast_contract_and_output.md)
- [Backtesting and model lifecycle](backtesting_and_model_lifecycle.md)
- [Demand data model](demand_data_model.md)
- [Scheduled forecast publication pipeline](scheduled_forecast_publication_pipeline.md)

{% enddocs %}
