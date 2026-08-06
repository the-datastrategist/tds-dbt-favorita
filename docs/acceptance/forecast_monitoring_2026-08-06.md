# Forecast monitoring acceptance — 2026-08-06

The mode-aware source and scheduled-pipeline monitoring slice passed live GCP acceptance in the
`tds-favorita` development environment on 2026-08-06. The acceptance used the immutable Favorita
snapshot and the previously accepted scheduled forecast publication run.

## Source ingestion evidence

| Evidence | Value |
|---|---|
| Ingestion run ID | `adf62329df085620d09247162e52b22295e80b8a084e4365f2ed0afee5086bf7` |
| Source | `favorita_sales` |
| Source table | `tds-favorita.raw_favorita.raw_favorita_train` |
| Watermark column | `date` |
| Source watermark | `2017-08-15 00:00:00 UTC` |
| Ingested rows | `125,497,040` |
| Tables | `1` |
| Data mode | `static_demo` |
| Ingestion status | `succeeded` |
| Source policy hash | `e1009e26e57594ea952bd6d8e81aeb5992accbc28e35ccf78c1e086ffc9bdec4` |
| Loader code SHA | `9ce0f2e711a20b9642ce2f1c3a2ee6859b32e55e` |

The persisted policy hash exactly matched the hash calculated from
`vertex/config/source_monitoring.yaml`. `forecast_source_health` returned:

| Signal | Result |
|---|---|
| Health status | `healthy_static` |
| Alerting | `false` |
| Reason | `static_dataset_freshness_not_applicable` |

This confirms that the platform retains execution, watermark, row-count, policy, and lineage
controls without treating the intentionally historical demonstration watermark as a wall-clock
freshness failure.

## Scheduled pipeline health

| Evidence | Value |
|---|---|
| Forecast run ID | `5f0d24e3d3a39152125cac35e00ea52eee51cd2f36d495c8e02a26165c9b59ca` |
| Forecast contract | `store_daily_demand_h7_publication` |
| Run status | `draft` |
| Monitoring health status | `healthy` |
| Stages / unsuccessful stages | `5 / 0` |
| Maximum stage position | `5` |
| Blocking / failed blocking checks | `3 / 0` |
| Declared / persisted / distinct outputs | `54 / 54 / 54` |
| Distinct canonical keys | `54` |
| Horizons | `[7]` |
| Missing quantiles | `0` |
| Invalid quantile order | `0` |
| Invalid target-date offsets | `0` |
| Rows missing required provenance | `0` |

The authoritative stage sequence was:

```text
1:score -> 2:route -> 3:calibrate -> 4:reconcile -> 5:validate
```

Every stage had status `completed`, read 54 rows, and emitted 54 rows. The blocking checks
`point_in_time_cutoff`, `prediction_completeness`, and `quantile_ordering` passed. Prediction
completeness was `1.0` at a threshold of `1.0`.

## Defects corrected during acceptance

The first live health query incorrectly classified the accepted run as failed even though its
stages, gates, and outputs were valid. Two status-vocabulary mismatches caused the false alert:

1. Scheduled publication intentionally ends with `forecast_runs.run_status = 'draft'`, while the
   health mart initially accepted only `succeeded`.
2. Scheduled stages persist `stage_status = 'completed'`, while the health mart initially accepted
   only `succeeded`.

The mart now treats `succeeded` and `draft` as successful run outcomes and `completed` as the
successful stage outcome. All other run and stage statuses remain fail-closed. A dbt unit test
proves that a validated draft is healthy and an explicitly failed run remains failed.

## Validation execution

`make selector-forecast-monitoring` rebuilt the three selected views and ran the complete selected
test set after the correction:

```text
PASS=28 WARN=0 ERROR=0 SKIP=0 NO-OP=0 REUSED=0 TOTAL=28
```

The run included 22 data tests and the new lifecycle regression unit test.

## Verification queries

Source health:

```sql
select
  source_name,
  source_policy_hash,
  data_mode,
  status,
  source_watermark,
  ingested_row_count,
  table_count,
  health_status,
  is_alerting,
  health_reason
from `tds-favorita.favorita.forecast_source_health`;
```

Pipeline health:

```sql
select
  forecast_run_id,
  forecast_contract_name,
  run_status,
  stage_count,
  unsuccessful_stage_count,
  maximum_stage_position,
  blocking_check_count,
  failed_blocking_check_count,
  row_count,
  persisted_output_count,
  distinct_output_count,
  horizon_count,
  missing_quantile_count,
  health_status
from `tds-favorita.favorita.forecast_pipeline_health`;
```

The detailed stage, gate, and output verification queries remain documented in
[scheduled_forecast_publication_2026-08-05.md](scheduled_forecast_publication_2026-08-05.md).
