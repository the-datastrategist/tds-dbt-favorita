# Demand data model acceptance — 2026-08-11

The canonical demand and eligibility slice passed live BigQuery acceptance in the `tds-favorita`
development environment.

## Contract semantics

The reference adapter declares `observed_sales_only`. Because Favorita provides no inventory feed,
the canonical relation retains `has_inventory_data = false`, null stockout/censoring fields, and
`availability_status = 'availability_not_provided'`. Observed sales are therefore a documented
proxy, not a claim of unconstrained demand.

The forecast contract already persists and hashes `demand_policy`; changing the policy creates a
different contract version.

## Validation execution

The `demand_data` selector built four views and ran its unit and data tests:

```text
PASS=28 WARN=0 ERROR=0 SKIP=0 NO-OP=0 REUSED=0 TOTAL=28
```

The unit fixture covered insufficient history, a healthy entity, stockout exclusion under
`exclude_stockout_days`, store closure, and inactive product precedence.

## Live eligibility evidence

The latest three reference forecast dates each returned:

| Signal | Value |
|---|---:|
| Candidate stores | `54` |
| Eligible stores | `54` |
| Excluded stores | `0` |
| Eligibility ratio | `1.0` |
| Demand policy | `observed_sales_only` |

The latest persisted runs for both the base and hierarchical publication contracts joined to the
same origin-date counts. Their `eligibility_snapshot_id` values were non-null and every sampled
row returned `eligibility_evidence_status = 'complete'`.

## Controls established

- Required history defaults to 28 observed days and is configurable.
- Every candidate has one deterministic eligibility decision and at most one exclusion reason.
- Store closure, product inactivity, assortment exclusion, and policy-controlled stockout precede
  history checks.
- Unknown inventory is not treated as in-stock.
- Run reporting exposes candidate, eligible, and excluded counts plus reason counts and a bounded
  exclusion sample.
- The existing scheduled pipeline rejects predictions that differ from the pinned eligibility
  snapshot.

## Remaining scope

The reference dataset cannot live-accept inventory, assortment, lifecycle, price, or closure
adapters because those sources are absent. Production adoption must map those interfaces with
effective-time/cutoff evidence. Row-level exclusion evidence should also be persisted immutably
against each run rather than exposed only through the deterministic dbt relation and summary.
