# Canonical identity migration acceptance — 2026-08-24

The canonical dataset adapter and forecast identity migration passed live acceptance in
`tds-favorita.favorita` after [PR #64](https://github.com/the-datastrategist/tds-dbt-favorita/pull/64)
merged to `main`.

## Deployment order and results

1. The idempotent Vertex BigQuery DDL added `series_key`, `entity_key_json`, and
   `target_timestamp` fields to prediction, forecast-output, and reconciliation evidence.
2. The canonical series, observation, feature, eligibility, and forecast-output staging models
   built successfully. Their selected suite completed with 75 passes and no errors.
3. Publication, realized-calibration, and operations-FVA marts completed with 20 passes and no
   errors.
4. The complete forecast-monitoring selector completed with 131 passes and no errors.

## Canonical publication acceptance

| Evidence | Value |
|----------|-------|
| Source prediction run | `410fa5e675d1d722b7bc308dacf66467673be007fd2b74bcd9d9338b66f5e559` |
| Accepted forecast run | `b243d1c631c9f32c8fbe047badec3ea19fd0c88490aa775d491dfb02aeae1bc1` |
| Source predictions | 54 |
| Canonical outputs | 54 |
| Distinct series | 54 |
| Distinct series/timestamp/horizon keys | 54 |
| Approvals | 54 |
| Publications | 54 |
| Missing lineage or delivery status | 0 |
| Invalid horizons or quantile ordering | 0 |
| Inconsistent series/entity mappings | 0 |

The acceptance command read the latest complete horizon-7 prediction batch, persisted a new
canonical batch, auto-published it, and queried the physical output and lifecycle tables. The
accepted rows therefore prove that new writes persist canonical identity directly rather than
relying on compatibility projections.

## Migration defects corrected

Live validation identified two historical-boundary conditions:

- Future scoring rows correctly have `target_observed = false` and a null target. The canonical
  test now requires a target only when `target_observed = true`.
- Pre-migration forecast rows do not physically contain the newly introduced canonical columns.
  `stg_forecast_outputs` now derives `target_timestamp` from `target_date` and a stable
  `series_key` from `entity_key_json` for those immutable rows. New physical writes are still
  checked directly by live acceptance.

The build also found one 55-row historical run whose immutable outputs existed without its
`forecast_runs` parent record. An idempotent append reconstructed that registry record from the
existing output evidence; no forecast output was updated or deleted. The enforced referential
test passed afterward.

## Conclusion

Canonical identity now spans live scoring output, publication, reconciliation persistence,
retrieval staging, realized calibration, FVA, and monitoring. The next generalization increment
is migration of the remaining training and prediction families, followed by hierarchy and period
adapters.
