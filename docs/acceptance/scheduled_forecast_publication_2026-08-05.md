# Scheduled forecast publication acceptance — 2026-08-05

The governed horizon-7 champion-to-draft path passed live GCP acceptance in the
`tds-favorita` development environment on 2026-08-05. The accepted run executed scoring,
routing, split-conformal calibration, no-op reconciliation, and blocking validation before
making one complete draft atomically visible.

## Accepted run

| Evidence | Value |
|---|---|
| Forecast run ID | `5f0d24e3d3a39152125cac35e00ea52eee51cd2f36d495c8e02a26165c9b59ca` |
| Source prediction run ID | `7aa1ee141b73729e8271e1e8bf16370b1b9ec7910679dc5893d0ebf77908a2ca` |
| Forecast contract | `store_daily_demand_h7_publication` |
| Forecast contract hash | `91544443ebf1b170fa99addcceefb74022e2f8db85478c3f1af1fe5d0dd4ebf5` |
| Forecast origin | `2017-08-16` |
| Data cutoff | `2017-08-16` |
| Code SHA | `9cd2a799d19da8e0744ac0ef802b7aff643bc543` |
| Feature-availability hash | `36e5c0ec7a71819e27a0e798f47ed5f8c44bc6469749da4d5b09dbc0e2896155` |
| Feature version | `0b3945bb16a5965bf29e13f2bffb32135a5a32a0cdcd479e7fa6faa0e50c17c9` |
| Feature materialization / eligibility snapshot | `ec3a5a1192f5890e7c838fef74ec40f6efd3c2659a31589ef05ee2a6e5003c6c` |
| Champion candidate | `d1b4751b300262860e1773cddf49393b483050dcfd3fb72f3457af749fc0aed1` |
| Backtest run | `13e7d615b1ee837ea739b44ae36c2ce1085bb479b050bfbc00d60b78e1f1832c` |
| Model run | `cb4e2f1c1425c25f3df959538eae34a4052e7704a1dfe40eeee186feb7d7ae49` |
| Model ID | `9b4cb14c1b2c2c0659e617c4a76174deaa3d03553ac7760f19dc739c228f879b` |
| Model artifact | `gs://favorita-vertex-models/favorita_store_h7_xgboost/xgboost_sklearn_favorita_store_h7_xgboost_20260725T050611/model.json` |

The champion was promoted by `prefect-model-lifecycle` in lifecycle event
`92b37e73526c1231047bc49a1fafa0845f4c872660ba1552b77550cf6a67053a`.

## Acceptance results

| Gate | Result |
|---|---:|
| Run status | `draft` |
| Declared/output/distinct output rows | `54 / 54 / 54` |
| Distinct canonical keys | `54` |
| Source prediction runs | `1` |
| Horizons | `[7]` |
| Invalid target-date offsets | `0` |
| Missing quantiles | `0` |
| Invalid P10/P50/P90 ordering | `0` |
| Rows missing required output provenance | `0` |
| Completed/distinct stages | `5 / 5` |
| Stage cardinality mismatches | `0` |
| Validation checks | `3` |
| Failed blocking checks | `0` |

The authoritative stage order was:

```text
1:score -> 2:route -> 3:calibrate -> 4:reconcile -> 5:validate
```

Every stage read and emitted 54 rows. Adjacent stages are chained by matching persisted output and
input fingerprints. The blocking checks `point_in_time_cutoff`, `prediction_completeness`, and
`quantile_ordering` all passed; prediction completeness was `1.0` at a threshold of `1.0`.

The persisted feature-availability hash matches the hash calculated directly from
`vertex/config/feature_availability.yaml` at the accepted code revision.

## Idempotency evidence

The same source prediction run was replayed with the same contract, champion, feature pins, and
code SHA. Stable identifiers made the second persistence attempt a no-op:

| Table | Rows | Distinct IDs |
|---|---:|---:|
| `forecast_runs` | 1 | 1 run ID |
| `forecast_pipeline_stage_runs` | 5 | 5 stage IDs |
| `forecast_validation_checks` | 3 | 3 check IDs |
| `forecast_outputs` | 54 | 54 output IDs |
| `forecast_status_history` | 54 | 54 status-event IDs |

No duplicate run, stage, check, output, or status record was created.

## Lineage defect corrected during acceptance

Run `7e01dc502496e12fc2ae282953605f99e000c4ffff8ef7ccb5b98d5087ac6325`
completed before this acceptance but persisted a null `feature_availability_hash`. The cause was a
missing field in `ForecastRunPins` plus an explicit null in scheduled-run persistence. Commit
`9cd2a799d19da8e0744ac0ef802b7aff643bc543` makes the registry hash a material run pin and persists
it. Seven focused regression tests passed before the corrected live replay.

The earlier row remains immutable and is not acceptance evidence. The corrected successor run
listed above is authoritative.

## Verification queries

Run-level lineage:

```sql
select
  forecast_run_id,
  forecast_contract_name,
  forecast_contract_hash,
  run_status,
  forecast_origin,
  data_cutoff,
  feature_availability_hash,
  feature_materialization_id,
  feature_version,
  code_sha,
  champion_candidate_id,
  model_run_id,
  model_id,
  row_count
from `tds-favorita.favorita.forecast_runs`
where forecast_run_id =
  '5f0d24e3d3a39152125cac35e00ea52eee51cd2f36d495c8e02a26165c9b59ca';
```

Stage order and cardinality:

```sql
select
  stage_position,
  stage_name,
  stage_status,
  component_run_id,
  input_row_count,
  output_row_count,
  input_fingerprint,
  output_fingerprint
from `tds-favorita.favorita.forecast_pipeline_stage_runs`
where forecast_run_id =
  '5f0d24e3d3a39152125cac35e00ea52eee51cd2f36d495c8e02a26165c9b59ca'
order by stage_position;
```

Blocking gates:

```sql
select
  check_name,
  severity,
  passed,
  observed_value,
  threshold_value,
  details_json
from `tds-favorita.favorita.forecast_validation_checks`
where forecast_run_id =
  '5f0d24e3d3a39152125cac35e00ea52eee51cd2f36d495c8e02a26165c9b59ca'
order by check_name;
```

Output invariants:

```sql
select
  count(*) as output_rows,
  count(distinct forecast_output_id) as distinct_output_ids,
  count(distinct to_json_string(struct(entity_key_json, target_date, horizon)))
    as distinct_canonical_keys,
  array_agg(distinct horizon order by horizon) as horizons,
  countif(date_diff(target_date, date(forecast_origin), day) != horizon)
    as invalid_target_dates,
  countif(prediction_p10 is null or prediction_p50 is null or prediction_p90 is null)
    as missing_quantiles,
  countif(prediction_p10 > prediction_p50 or prediction_p50 > prediction_p90)
    as invalid_quantile_order,
  countif(
    forecast_contract_hash is null or forecast_origin is null or target_date is null
    or forecast_strategy is null or confidence_flag is null or calibration_method is null
    or calibration_run_id is null or reconciliation_method is null or model_run_id is null
    or model_id is null or config_name is null or feature_version is null or code_sha is null
    or data_cutoff is null or model_artifact_uri is null
  ) as missing_output_provenance
from `tds-favorita.favorita.forecast_outputs`
where forecast_run_id =
  '5f0d24e3d3a39152125cac35e00ea52eee51cd2f36d495c8e02a26165c9b59ca';
```

Retry duplicate checks:

```sql
select
  (select count(*) from `tds-favorita.favorita.forecast_runs`
    where forecast_run_id = '5f0d24e3d3a39152125cac35e00ea52eee51cd2f36d495c8e02a26165c9b59ca')
    as run_rows,
  (select count(*) from `tds-favorita.favorita.forecast_pipeline_stage_runs`
    where forecast_run_id = '5f0d24e3d3a39152125cac35e00ea52eee51cd2f36d495c8e02a26165c9b59ca')
    as stage_rows,
  (select count(*) from `tds-favorita.favorita.forecast_validation_checks`
    where forecast_run_id = '5f0d24e3d3a39152125cac35e00ea52eee51cd2f36d495c8e02a26165c9b59ca')
    as check_rows,
  (select count(*) from `tds-favorita.favorita.forecast_outputs`
    where forecast_run_id = '5f0d24e3d3a39152125cac35e00ea52eee51cd2f36d495c8e02a26165c9b59ca')
    as output_rows,
  (select count(*) from `tds-favorita.favorita.forecast_status_history`
    where forecast_run_id = '5f0d24e3d3a39152125cac35e00ea52eee51cd2f36d495c8e02a26165c9b59ca')
    as status_rows;
```
