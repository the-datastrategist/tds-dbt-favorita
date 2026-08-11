{% docs spec_hierarchical_reconciliation %}

# SPEC: Hierarchical reconciliation

**Status:** Shipped
**Roadmap reference:** [Specs overview](README.md) — P1 "Add hierarchical reconciliation"

---

## Summary

The repo currently materializes features at several grains, but independently trained forecasts at several grains are not the same as coherent hierarchical forecasts. This spec adds a hierarchy configuration, reconciliation methods, and a published-output guarantee that company, store, family, and SKU forecasts add up according to the selected policy.

## Goals

- Document hierarchy concepts in `docs/hierarchical_reconciliation.md`.
- Add a hierarchy configuration model for levels, keys, parent-child relationships, and allocation weights.
- Implement bottom-up, top-down, middle-out, and MinT/variance-weighted reconciliation where data supports it.
- Persist both base forecasts and reconciled forecasts.
- Validate that published forecasts reconcile within tolerance.

## Non-goals

- Changing the existing `int_sales_*` feature grains by default.
- Requiring SKU-level forecasts for every dataset. The hierarchy config should support whatever levels a contract declares.
- Inventory allocation optimization.

## Design

### 1. Documentation

Add `docs/hierarchical_reconciliation.md` explaining:

- base forecast vs reconciled forecast
- level definitions
- supported methods
- reconciliation tolerance
- when to use each method

### 2. Hierarchy config

Example:

```yaml
hierarchy:
  name: retail_demand
  levels:
    - name: company
      keys: []
    - name: store
      keys: [store_id]
    - name: product_family
      keys: [store_id, product_family]
    - name: product
      keys: [store_id, product_id]
  reconciliation:
    method: bottom_up
    tolerance_abs: 0.01
```

### 3. Hierarchy tables

Minimum tables/marts:

| Table | Purpose |
|-------|---------|
| `forecast_hierarchy_nodes` | Node IDs and attributes |
| `forecast_hierarchy_edges` | Parent-child relationships |
| `forecast_reconciliation_runs` | Reconciliation metadata |
| `forecast_reconciled_outputs` | Reconciled forecasts by node/horizon/origin |

### 4. Reconciliation methods

Initial implementation order:

1. `bottom_up`: aggregate lowest available grain.
2. `top_down`: allocate aggregate forecast by historical or configured proportions.
3. `middle_out`: reconcile from a configured middle level.
4. `mint`: use residual covariance from backtests where enough history exists.

### 5. Validation

Add dbt tests:

- every child has one parent per hierarchy version
- no cycles
- published reconciled child sums equal parent totals within tolerance
- no orphan nodes for eligible forecast rows

### 6. Scheduled publication integration

Reconciliation consumes calibrated base forecasts and is the final numerical transformation before
publication validation. When quantiles are configured, it reconciles every quantile and must
preserve both hierarchy coherence and `P10 <= P50 <= P90`. It emits the canonical forecast keys,
`hierarchy_version`, `reconciliation_method`, and `reconciliation_run_id`, while retaining the
unreconciled values for audit and metric comparison.

Quantile ordering and coherence must be satisfied jointly; sorting each node's quantiles after
reconciliation is prohibited because it can break parent-child totals. Failure to converge within
the configured tolerances blocks publication for the affected scope, and the flow must not
substitute unreconciled forecasts silently. Contracts with no hierarchy explicitly record method
`none`. Ordering, partial-failure policy, and publication gates are defined by the authoritative
[scheduled forecast publication pipeline](scheduled_forecast_publication_pipeline.md).

## Implementation plan

1. Add `docs/hierarchical_reconciliation.md`.
2. Add hierarchy config loader and validation.
3. Add dbt models for hierarchy nodes/edges for the current project implementation.
4. Implement bottom-up reconciliation first.
5. Add top-down and middle-out allocation.
6. Add MinT once backtest residual covariance is available.
7. Route published forecasts through reconciliation before publication.

## Current implementation

Hierarchy validation, bottom-up, top-down, middle-out, and MinT reconciliation are implemented.
The scheduled pipeline loads the pinned hierarchy version when the forecast contract declares a
reconciliation policy, reconciles every configured quantile before validation, and prevents an
incoherent result from becoming a visible draft. The Favorita `company -> store` hierarchy has
passed live champion-to-draft acceptance, including graph integrity, eligible-node membership,
P10/P50/P90 coherence and ordering, reconciliation lineage, and fail-closed behavior. Base and
reconciled values are stored as separate append-only records linked to the canonical output, and
base-versus-reconciled MAE/WAPE are persisted by hierarchy level and horizon. An identical live
retry reused the logical run and row identities without creating duplicates. See the
[2026-08-10 acceptance evidence](../acceptance/hierarchical_reconciliation_2026-08-07.md).

## Testing & validation

- Unit tests for hierarchy graph validation.
- Fixture test with known child forecasts and expected parent totals.
- dbt reconciliation tolerance test.
- Backtest comparison of base vs reconciled metrics by level.

## Acceptance criteria

- A hierarchy config can be validated for the current project implementation.
- Published forecasts reconcile from lowest available level to company total.
- Reconciled and unreconciled forecasts are separately queryable.

All acceptance criteria are satisfied for the reference Favorita implementation.

## Related documents

- [Forecast contract and canonical output](forecast_contract_and_output.md)
- [Forecasting methods](forecasting_methods.md)
- [Integration contracts](integration_contracts.md)
- [Forecast operations](forecast_operations.md)
- [Scheduled forecast publication pipeline](scheduled_forecast_publication_pipeline.md)

{% enddocs %}
