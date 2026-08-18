# Forecast data drift acceptance — 2026-08-11

Feature and target drift monitoring passed controlled and live BigQuery acceptance.

`forecast_data_drift` compares the latest 28-day window with the immediately preceding 28-day
window for every metric in `drift_monitored_metrics`. The reference deployment monitors canonical
observed demand as a target and seven-day average store sales as a feature. Deployments can add
metrics without changing the mart.

The signal uses absolute standardized mean difference with a default maximum of `0.50`. It requires
at least 30 non-null observations in each window. A metric with insufficient evidence is
`insufficient_observations` and non-alerting. A zero-variance metric alerts when its mean moves,
instead of silently producing a null standardized difference.

The controlled fixture proved both a constant target-level shift and a stable feature distribution.
The focused live dbt build created the view and passed its unit and schema tests:

```text
PASS=12 WARN=0 ERROR=0 SKIP=0 TOTAL=12
```

Focused Python monitoring tests passed (`7 passed`), including ticket routing and deterministic
`source_model:metric_name` resource identity.

The complete live forecast-monitoring selector passed (`PASS=111`, `WARN=0`, `ERROR=0`,
`SKIP=0`). The full unit suite passed (`370 passed`, `7 deselected`) with 76.37% coverage.
The live evaluator loaded the drift view successfully and emitted no drift alerts. Its only dry-run
events were existing pipeline-health alerts for forecast runs that predate eligibility evidence.
