# Core forecasting acceptance — 2026-07-18

The horizon-aware forecasting, baseline, and rolling-origin ML-scoring contract passed its
local and live GCP acceptance gates on 2026-07-18.

## Evidence

- `make vertex-backtest-persist` completed successfully against BigQuery and wrote the
  append-only backtest run, prediction, and metric contracts.
- `make dbt-backtest` completed successfully and validated the comparable leaderboard and
  champion models.
- The identical persistence contract is retry-safe through stable run, prediction, and metric
  identifiers and insert-only BigQuery merges.
- Local validation passed 241 unit tests at 77.11% coverage, including 67 focused forecasting,
  backtesting, calibration, routing, reconciliation, and lifecycle tests.

Durable run identifiers and timestamps are retained in `backtest_runs`; prediction and metric
evidence joins through `backtest_run_id` to `backtest_predictions` and `backtest_metrics`.

## Acceptance query

```sql
select
  runs.backtest_run_id,
  runs.status,
  runs.prediction_count,
  runs.metric_count,
  count(distinct predictions.prediction_id) as persisted_predictions,
  count(distinct metrics.metric_id) as persisted_metrics
from `tds-favorita.favorita.backtest_runs` as runs
left join `tds-favorita.favorita.backtest_predictions` as predictions using (backtest_run_id)
left join `tds-favorita.favorita.backtest_metrics` as metrics using (backtest_run_id)
group by 1, 2, 3, 4
order by runs.created_at desc
limit 1;
```
