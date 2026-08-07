# Hierarchical reconciliation acceptance — 2026-08-07

The Favorita `company -> store` hierarchy passed live acceptance in the `tds-favorita`
development environment on 2026-08-07. The scheduled publication pipeline scored the pinned
champion, routed and calibrated its forecasts, reconciled all configured quantiles with
`bottom_up`, applied blocking validation, and atomically exposed a coherent draft.

## Accepted run

| Evidence | Value |
|---|---|
| Forecast run ID | `bc8040556a3bc509b39a66fc06eee013eddd239ecbdba2b7da740631f5bd5199` |
| Source prediction run ID | `410fa5e675d1d722b7bc308dacf66467673be007fd2b74bcd9d9338b66f5e559` |
| Forecast contract | `favorita_store_daily_demand_h7_hierarchical_publication` |
| Forecast contract hash | `cb70c27e8e278de58243e466d77f6e03e019f5d3de76b388488fdf6743f63d43` |
| Hierarchy | `favorita_demand` |
| Hierarchy version | `v1` |
| Hierarchy hash | `2d5c352f77878c866a8c70e01e5f9808f059c8509639d85c963f73192b1d1e1d` |
| Reconciliation method | `bottom_up` |
| Absolute tolerance | `0.01` |
| Forecast origin / data cutoff | `2017-08-16 / 2017-08-16` |
| Code SHA | `c900ca11f953c3078b1099f0726afb23e5ea8600` |
| Model run ID | `cb4e2f1c1425c25f3df959538eae34a4052e7704a1dfe40eeee186feb7d7ae49` |
| Model ID | `9b4cb14c1b2c2c0659e617c4a76174deaa3d03553ac7760f19dc739c228f879b` |

The authoritative stage order was:

```text
1:score -> 2:route -> 3:calibrate -> 4:reconcile -> 5:validate
```

All five stages completed. The resulting run is a 55-row canonical draft. Final approval and
delivery remain separate forecast-operation transitions; this acceptance validates the scheduled
champion-to-draft publication boundary.

## Acceptance results

| Invariant | Result |
|---|---:|
| Hierarchy configuration validates and matches the contract | Passed |
| Hierarchy nodes / roots / leaves | `55 / 1 / 54` |
| Edges | `54` |
| Children with exactly one parent | `54` |
| Cycles or unreachable cyclic components | `0` |
| Orphan forecast nodes | `0` |
| Eligible leaves missing forecasts | `0` |
| Configured quantiles | `[0.1, 0.5, 0.9]` |
| Rows missing a configured quantile | `0` |
| P10 coherence violations | `0` |
| P50 coherence violations | `0` |
| P90 coherence violations | `0` |
| Invalid `P10 <= P50 <= P90` rows | `0` |
| Rows missing reconciliation lineage | `0` |
| Rows with wrong hierarchy version or method | `0` |
| Controlled reconciliation failure blocked | Passed |

Every canonical row contains `hierarchy_version = 'v1'`,
`reconciliation_method = 'bottom_up'`, and a non-null `reconciliation_run_id`.

## Fail-closed evidence

The acceptance command appends a duplicate parent assignment to an in-memory copy of the accepted
graph and invokes the same reconciliation entrypoint used by the scheduled stage. Graph validation
raises `every hierarchy child must have exactly one parent` before reconciliation can return rows
for persistence. The scheduled flow calls its persistence boundary only after reconciliation and
all blocking validation complete, so this failure cannot create a visible draft.

The focused hierarchy, pipeline, and orchestration suite also passed 16 tests, including graph
validation, coherent quantile reconciliation, hierarchy expansion, and scheduled persistence
ordering.

## Repeatable verification

Run the acceptance validator against the immutable run:

```bash
make vertex-hierarchy-accept \
  FORECAST_RUN_ID=bc8040556a3bc509b39a66fc06eee013eddd239ecbdba2b7da740631f5bd5199
```

The command loads the pinned YAML contract and hierarchy, reads the versioned graph and canonical
rows from BigQuery, validates graph structure and forecast membership, checks every configured
quantile for coherence and ordering, verifies reconciliation lineage, and executes the controlled
fail-closed probe.

## Superseded pre-commit draft

Run `a72de378cd6a3c74a5c49049d7acaa32e4329aaf530b078bb037d4a05fe5318b`
passed the same numerical invariants while the hierarchy changes were still uncommitted. It is not
acceptance evidence because its persisted `code_sha` predates the implementation. The run listed
above was executed from commit `c900ca1` and is authoritative.
