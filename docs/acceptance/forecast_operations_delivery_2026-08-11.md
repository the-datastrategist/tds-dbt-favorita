# Forecast operations and delivery acceptance — 2026-08-11

## Scope

This acceptance validates the stable warehouse views, immutable planner operations, versioned
publication lineage, and explicit-version Parquet delivery contract against the live
`tds-favorita.favorita` dataset.

## Accepted source run

| Field | Value |
|---|---|
| Forecast run | `c9529665c1a5ec945e799272e1f77d8da9b645732d741e6b88e5c1e79f6d3b3f` |
| Contract | `favorita_store_daily_demand_h7_hierarchical_publication` |
| Canonical outputs | 55 |
| Operator | `codex-live-acceptance` |

The run previously passed scheduled publication and hierarchy acceptance. Every published row in
this acceptance retained `hierarchy_version`, `reconciliation_method`, and
`reconciliation_run_id`; no published row had unordered P10/P50/P90 values.

## CI and deployment

- PR [#45](https://github.com/the-datastrategist/tds-dbt-favorita/pull/45) merged after Python,
  dbt, dependency-audit, secret-history, container-scan, and SBOM checks passed.
- `published_forecasts_current`, `published_forecasts_by_run`,
  `forecast_publication_audit`, and `forecast_overrides_audit` were deployed with dbt:
  `PASS=6 WARN=0 ERROR=0 SKIP=0` (four views and two hooks).

## Operation evidence

One immutable planner override changed output
`01a5d67367631edb745b1c3aa2c86815ef9c222b0a4ff7a7d33681de41729a11` from
20,737.771484375 to 20,738.771484375. Replaying idempotency key
`acceptance-c952-override-v1` returned the existing override
`a455f34fbdb8ea82835f650469851552c350b936791a55b4ff174f47d8e97418`.

| Version | Action | Publications | Revision records | Result |
|---:|---|---:|---:|---|
| 1 | approve and publish | 55 | 0 | Complete; identical retry returned the existing 55 rows |
| 2 | revise version 1 | 55 | 55 | Complete |
| 3 | roll back version 1 | 55 | 55 | Complete and current |

Warehouse validation returned:

- 55 rows and 55 distinct outputs in each of versions 1, 2, and 3;
- 55 rows and 55 distinct outputs in `published_forecasts_current`, all at version 3;
- zero missing hierarchy/reconciliation provenance values;
- zero unordered quantile rows;
- one immutable override represented by two expected audit rows, one for each approval in versions
  1 and 2;
- 220 publication-audit rows, including both sides of revision relationships.

## Export evidence

Version 3 was exported as Parquet to:

```text
gs://favorita-vertex-staging/acceptance/forecast-delivery-2026-08-11/c952-v3-*.parquet
```

The delivery contains five shards, 74,004 bytes, and exactly 55 rows. Replaying the same export
failed closed because the destination was non-empty; no object was replaced.

Live acceptance identified and fixed an ambiguity in the original command: an export now requires
both `forecast_run_id` and `publication_version`. This prevents a revised run from combining
multiple immutable versions in one artifact.

## Result

**Accepted.** The warehouse and Parquet delivery boundaries are reproducible, version-pinned,
auditable, idempotent where records are persisted, and fail closed where artifacts are immutable.
Delivery-status confirmation and service/webhook adapters remain owned by the integration roadmap.
