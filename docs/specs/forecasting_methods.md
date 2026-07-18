{% docs spec_forecasting_methods %}

# SPEC: Forecasting methods, horizons, cold start, and intermittent demand

**Status:** In progress
**Roadmap reference:** [`demand_forecasting_platform_recommendations.md`](../demand_forecasting_platform_recommendations.md) — P0 "Implement multi-horizon forecasting", P1 "Add probabilistic forecasts", and P1 "Add cold-start and intermittent-demand routing"

---

## Summary

The current default Vertex config is framed around `n1d` next-day scoring. The platform needs explicit multi-horizon strategy, probabilistic outputs, and routing for sparse, intermittent, short-history, and cold-start series.

This spec adds `docs/forecasting_methods.md`, horizon-aware scoring, quantile support, conformal calibration, and a strategy router that records how each forecast row was produced.

## Goals

- Define supported multi-horizon strategies: direct, recursive, multi-output, and global model.
- Make `n1d` explicitly a one-day model or replace it with horizon-aware configs.
- Generate forecasts for configured horizons and evaluate by horizon.
- Support configurable quantiles, at minimum P10/P50/P90.
- Add a model-agnostic conformal prediction path.
- Route cold-start and intermittent-demand series through explicit fallback strategies.
- Persist selected strategy on each forecast row.

## Non-goals

- Deep learning model families. They can implement this interface later.
- Inventory optimization or safety-stock calculation. Quantiles are produced for those consumers but not consumed here.
- Full hierarchy reconciliation. Reconciliation belongs in [hierarchical reconciliation](hierarchical_reconciliation.md).

## Design

### 1. Documentation

Add `docs/forecasting_methods.md` covering:

- local vs global models
- direct vs recursive vs multi-output multi-horizon strategies
- probabilistic forecast options
- intermittent demand methods
- cold-start fallback hierarchy
- how methods map to `model_config.yaml`

### 2. Horizon-aware config

Forecast contracts provide the canonical horizon list. Model configs should either inherit those horizons or declare an explicit supported subset.

Example:

```yaml
inputs:
  horizon_strategy: direct
  horizons: [1, 2, 3, 4, 5, 6, 7, 14, 28]
  quantiles: [0.1, 0.5, 0.9]
```

Validation should reject configs that claim multi-horizon output but emit only one horizon.

### 3. Probabilistic forecasts

Support two paths:

| Path | Use case |
|------|----------|
| model-native intervals | Prophet or time-series families that emit intervals |
| conformal calibration | model-agnostic intervals from historical residuals |

Canonical output should write P10/P50/P90 or normalized quantile rows. Evaluation should compute pinball loss, coverage, and interval width by horizon/segment.

### 4. Series classification

Add a classifier that writes one row per entity/target/grain:

```text
entity_key_json
history_length
nonzero_observation_count
average_demand_interval
coefficient_of_variation_squared
is_intermittent
is_cold_start
recommended_strategy
classification_run_id
```

### 5. Fallback routing

Implement strategy order:

1. Entity-specific model where sufficient history exists.
2. Global model using store/product attributes.
3. Family/store-level forecast allocated to the entity.
4. Seasonal/rate-based baseline.
5. Configured business default with low-confidence flag.

Each `forecast_outputs` row must record:

```text
forecast_strategy
fallback_reason
confidence_flag
```

### 6. Scheduled publication integration

Strategy routing is the first model-selection stage of the scheduled publication path. It receives
eligible series plus the validated forecast contract and emits base forecasts with the canonical
keys, `forecast_strategy`, `fallback_reason`, and `confidence_flag`. Those rows then pass to
calibration before reconciliation; routing must not publish directly.

All configured quantiles must share the same selected strategy for a given entity, origin, target
date, and horizon. A routing failure may use only a fallback declared by the contract. Otherwise it
creates a forecast exception and blocks publication for that scope. Ordering, retries, frozen
eligibility, publication gates, and idempotency are defined by the authoritative
[scheduled forecast publication pipeline](scheduled_forecast_publication_pipeline.md).

## Implementation plan

1. Add `docs/forecasting_methods.md`.
2. Add horizon strategy and quantile fields to contract/config validation.
3. Extend prediction writers to emit horizon and quantile outputs.
4. Add conformal calibration utilities and tests.
5. Add series classification mart/job.
6. Add routing rules and strategy metadata to canonical output.
7. Update benchmarks to report metrics by horizon and strategy.

## Testing & validation

- Unit tests for horizon expansion and validation.
- Synthetic multi-horizon prediction test ensuring all requested horizons are emitted.
- Conformal interval test with expected coverage behavior on deterministic residual fixtures.
- Series classification tests for cold-start, intermittent, and sufficient-history cases.
- dbt tests for no missing strategy on forecast output rows.

## Acceptance criteria

- A default forecast contract can produce at least 7 horizons.
- Metrics are queryable by horizon.
- Forecast rows include quantiles or calibrated intervals.
- Cold-start and intermittent series receive explicit strategies and fallback reasons.

## Related documents

- [Forecast contract and canonical output](forecast_contract_and_output.md)
- [Backtesting and model lifecycle](backtesting_and_model_lifecycle.md)
- [Demand data model](demand_data_model.md)
- [Prophet model family](prophet_model_family.md)
- [Forecast operations](forecast_operations.md)
- [Scheduled forecast publication pipeline](scheduled_forecast_publication_pipeline.md)

{% enddocs %}
