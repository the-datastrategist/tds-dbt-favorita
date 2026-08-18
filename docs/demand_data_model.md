# Demand data model

The forecasting contract distinguishes recorded sales from unconstrained demand. In the reference
Favorita deployment, inventory and availability are not provided, so `observed_sales_only` is the
explicit demand policy: observed sales are a proxy for demand, stockouts cannot be identified, and
lost demand is not imputed. Forecasts must not be described as unconstrained demand estimates.

## Canonical interfaces

Production adapters should map source-specific tables into these semantics before changing the
demand policy:

| Interface | Required grain and fields | Availability |
|---|---|---|
| Sales | entity/date, observed units; revenue optional | Observed after the period |
| Inventory | entity/date, on-hand units, in-stock/stockout flag | Observed after the period |
| Assortment | entity, effective start/end, active flag | Static or planned-revisable |
| Product lifecycle | product, launch date, retirement date | Static master data |
| Price | entity/date, unit price, plan version | Historical or planned-revisable |
| Promotion | entity/date, flag/type, plan version | Known future only at its recorded cutoff |
| Closure/event | location/date, open flag, reason | Known future or planned-revisable |

`int_demand_store_daily` is the reference canonical relation. Missing optional feeds remain
explicit: `has_inventory_data = false`, availability is `availability_not_provided`, and stockout
and censoring flags are null rather than silently assumed false.

## Demand policies

- `observed_sales_only`: use sales as the demand proxy. This is the reference default.
- `exclude_stockout_days`: exclude confirmed stockout observations; requires inventory evidence.
- `impute_lost_demand_simple`: add a governed simple estimate; requires inventory evidence and a
  separately accepted imputation method.
- `external_unconstrained_demand`: consume a source-owned unconstrained-demand measure.

The policy is part of `vertex/config/forecast_contract.yaml` and its immutable contract hash.
Changing it creates a new forecast contract version.

## Eligibility

`forecast_eligibility` produces one decision per store/date with:

- stable `entity_key_json`
- `is_eligible` and one deterministic `ineligibility_reason`
- assortment, location, and lifecycle flags
- required-history evidence
- inventory/stockout evidence and demand policy

Exclusion precedence is store closure, inactive product, outside assortment, policy-controlled
stockout, missing history, then insufficient history. This makes counts reproducible and prevents
scoring from silently dropping entities. `forecast_eligibility_summary` publishes candidate,
eligible, and excluded counts plus reason counts and a bounded exclusion sample.

Run the slice with:

```bash
docker compose run --rm ml-pipeline dbt build \
  --project-dir dbt --profiles-dir dbt/profiles --target dev --selector demand_data
```

Before production scoring, select the eligibility row at the forecast origin, freeze the eligible
entity set, and persist its fingerprint as `forecast_runs.eligibility_snapshot_id`. The scheduled
pipeline already rejects prediction rows that differ from that pinned population.
`forecast_run_eligibility_summary` joins each persisted run to its origin-date candidate, eligible,
and excluded counts and flags missing snapshot IDs or missing summary evidence.

## Adapter requirements

When adding inventory, assortment, lifecycle, price, promotion, or closure sources:

1. Preserve source-effective timestamps and ingestion/cutoff evidence.
2. Never forward-fill a planned feature across a revision boundary without its plan version.
3. Keep unknown availability as unknown; do not translate it to in-stock.
4. Add unit fixtures for closure, retirement, assortment, and stockout behavior.
5. Compare eligible, forecasted, and excluded counts before allowing publication.
