{% docs spec_demand_data_model %}

# SPEC: Demand data model

**Status:** Proposed
**Roadmap reference:** [`demand_forecasting_platform_recommendations.md`](../demand_forecasting_platform_recommendations.md) — P1 "Handle demand-specific data conditions"

---

## Summary

The public Favorita dataset supports observed sales forecasting, but a demand forecasting platform must distinguish observed sales from unconstrained demand. This spec adds `docs/demand_data_model.md`, optional inventory/availability interfaces, lifecycle policies, and clear public-example language about forecasting sales as a demand proxy.

## Goals

- Define canonical demand-domain entities and facts.
- Distinguish observed sales, constrained demand, estimated lost demand, and unconstrained demand.
- Add optional interfaces for inventory, in-stock status, assortment, product lifecycle, prices, and promotions.
- Represent store closures, product launches, retirements, and eligibility dates.
- Document how Favorita behaves when stock/availability data is unavailable.

## Non-goals

- Replenishment optimization.
- Estimating lost demand perfectly. Initial implementation should support flags and simple policies, not claim causal inventory correction.
- Requiring every adopter to provide inventory data.

## Design

### 1. Documentation

Add `docs/demand_data_model.md` with:

- conceptual model
- required vs optional source tables
- public Favorita limitations
- stockout/censoring policies
- lifecycle/eligibility rules
- future covariate requirements

### 2. Canonical source interfaces

Define expected columns for optional tables:

| Interface | Key columns |
|-----------|-------------|
| sales | entity keys, date, observed sales units/revenue |
| inventory | entity keys, date, on hand, in stock flag |
| assortment | store/product, start date, end date, active flag |
| product lifecycle | product, launch date, retirement date |
| price history/plan | product/store, date, price, plan version |
| promotion history/plan | product/store, date, promotion flag/type, plan version |
| closures/events | store/date, closure flag, reason |

### 3. Eligibility policy

Add a model that computes eligible entity/date rows for forecasting:

```text
entity_key_json
date
is_eligible
ineligibility_reason
assortment_active
store_open
product_active
has_required_history
```

Forecast scoring should not silently omit entities; it should record excluded entities and reasons.

### 4. Censored demand policy

Support policy values:

- `observed_sales_only`
- `exclude_stockout_days`
- `impute_lost_demand_simple`
- `external_unconstrained_demand`

Favorita default: `observed_sales_only`.

### 5. Feature integration

The feature availability registry should mark inventory and actual sales as observed features, while price plans and promotion plans may be known-future or planned-revisable.

## Implementation plan

1. Add `docs/demand_data_model.md`.
2. Add source interface YAML examples.
3. Add eligibility dbt model and schema tests.
4. Add exclusion reason persistence to forecast runs/output.
5. Add Favorita-specific docs stating observed sales are used as demand proxy.
6. Update forecast contract validation to include demand policy.

## Testing & validation

- Unit/fixture tests for eligibility rules.
- dbt tests for unique entity/date eligibility rows.
- Fixture with store closure and product retirement exclusion.
- Smoke test showing excluded entity counts in forecast run metadata.

## Acceptance criteria

- Forecast runs can report eligible, forecasted, and excluded entity counts.
- Favorita docs clearly state that stockout-adjusted unconstrained demand is not available.
- Demand policy is explicit in the forecast contract.

## Related documents

- [Forecast contract and canonical output](forecast_contract_and_output.md)
- [Point-in-time feature availability](point_in_time_feature_availability.md)
- [Forecasting methods](forecasting_methods.md)

{% enddocs %}
