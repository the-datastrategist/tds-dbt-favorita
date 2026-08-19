# Forecast monitoring and source freshness

This platform treats source freshness as a property of the source contract, not as a comparison
between today's date and the maximum event date. That distinction allows the bundled Favorita
snapshot to remain a valid demonstration dataset while preserving the controls needed for a source
that receives new data continually.

## Source modes

Source policies live in `vertex/config/source_monitoring.yaml`.

| Mode | Freshness behavior | What still alerts |
|---|---|---|
| `static_demo` | Wall-clock staleness is not applicable. A historical watermark is expected. | Missing ingestion evidence, failed or partial latest load, invalid policy, and downstream pipeline failures. |
| `continuous` | The latest successful load must finish within `expected_interval_hours + allowed_lateness_hours`. | Missed ingestion window, failed or partial latest load, and all downstream failures. |

Both modes persist the source watermark, row count, source location, code SHA, and policy hash. A
future client can switch to continuous behavior by changing the source policy; monitoring code and
warehouse contracts do not need to change.

These timestamps have separate meanings:

- `source_watermark` is the greatest source event time included in the load.
- `started_at` and `finished_at` describe loader execution time.
- `created_at` records when BigQuery accepted the evidence row.
- `evaluated_at` is the time at which the health mart evaluated the policy.

## Recording ingestion evidence

Apply `vertex/ddl/vertex_bq_tables.sql` before recording a run. Every loader or ingestion
orchestrator should append one record on success, partial completion, or failure. For the Favorita
snapshot:

```bash
make source-ingestion-record \
  SOURCE=favorita_sales \
  STATUS=succeeded \
  WATERMARK=2017-08-15T00:00:00Z \
  ROW_COUNT=125497040
```

Use `ARGS='--source-uri gs://bucket/path'` to add source lineage. The stable ingestion ID makes an
identical retry a no-op while changed attempts remain append-only.

## Health views

Run the monitoring slice after ingestion and scheduled forecasting:

```bash
make selector-forecast-monitoring
```

- `forecast_source_health` exposes the latest loader result per source and applies mode-aware
  freshness semantics.
- `forecast_pipeline_health` exposes the latest forecast run per contract and checks run/stage
  success, blocking gates, output cardinality, duplicate output IDs, and required quantiles.
  It also reconciles the immutable eligibility ledger to the run and outputs, alerting on missing
  evidence, snapshot mismatch, unexplained exclusions, count drift, or eligible candidates omitted
  from predictions.
- `forecast_prediction_coverage` compares the latest run's distinct output count with its frozen
  expected cardinality and alerts on missing predictions or coverage below the configured ratio.
- `forecast_feature_completeness` checks configured required columns on the latest in-scope
  feature date and compares entity coverage with the prior date. Removed columns fail at dbt
  compilation; null degradation and entity loss emit runtime alerts. Configure relations, columns,
  and optional row scope through `feature_completeness_monitored_models`.
- `forecast_publication_freshness` detects contracts with no publication and publications older
  than the configured maximum age. Delivery confirmation is exposed separately and does not
  weaken the freshness result. Contracts opt in through `publication_monitored_contracts`; this
  prevents draft-only and retired contracts from generating false stale-publication alerts.
- `ml_prediction_accuracy_rolling` remains the existing model-accuracy and drift signal and is run
  with `make selector-accuracy-monitoring`.
- `forecast_realized_calibration` joins matured store-level forecast intervals to canonical
  observed demand and reports P10-P90 coverage, median bias, normalized median bias, and mean
  interval width by contract and horizon. `insufficient_actuals` is non-alerting; once the minimum
  sample is met, `under_coverage` and `material_bias` route tickets.
- `forecast_data_drift` compares the latest configured target and feature windows with the
  immediately preceding windows. It emits `drifted` when standardized mean difference exceeds
  policy and treats `insufficient_observations` as non-alerting.
- `forecast_pipeline_cost` aggregates normalized cost events by forecast run, reports BigQuery and
  Vertex spend, cost per thousand outputs, allocation-label completeness, and historical anomalies.
  `cost_data_unavailable` and `insufficient_history` are non-alerting readiness states.

For deterministic validation, pass a timestamp to dbt with
`--vars '{monitoring_evaluated_at: "2026-08-05 12:00:00+00"}'`.

## Recording cost evidence

Billing-export adapters and forecast jobs should append one normalized event per source charge.
The source identity makes an identical retry a no-op:

```bash
make forecast-cost-record ARGS='\
  --service-name bigquery --cost-type query \
  --usage-start-at 2026-08-11T08:00:00Z --usage-end-at 2026-08-11T08:01:00Z \
  --amount-usd 0.42 --source-system billing_export --source-event-id invoice-line-123 \
  --forecast-contract-name store_daily --forecast-run-id run-123 \
  --stage-name score --environment prod --bytes-processed 1073741824'
```

Record credits as source-adjusted nonnegative net events; negative events are rejected so the mart
cannot silently invert spend. Preserve the provider's raw identifiers in `source_event_id` and
additional allocation metadata in `--labels-json`.

## Operating expectations

For this demonstration repository, run ingestion evidence once after loading the immutable raw
snapshot and again only if the snapshot or loader changes. Run pipeline health after every forecast
execution. In a continuously updating deployment, invoke the same evidence writer from every
scheduled or event-driven loader and run the monitoring selector after each load and forecast run.

## SLO catalog

The versioned contract in `vertex/config/monitoring.yaml` is authoritative. Defaults are suitable
for the reference deployment and must be reviewed per client.

| SLO | Default objective | Default threshold | Owner |
|---|---:|---:|---|
| Publication freshness | 99% over 30 days | Latest publication no older than 1,440 minutes | Forecasting operations |
| Prediction coverage | 99% over 30 days | At least 98% of frozen expected outputs | Forecasting operations |
| Pipeline availability | 99% over 30 days | Terminal within 120 minutes | ML platform |
| Realized calibration | 99% over 28 days | At least 80% P10-P90 coverage after 30 actuals | Forecasting science |
| Data drift | 99% over 28 days | Standardized mean difference no greater than 0.50 after 30 observations per window | Forecasting science |
| Pipeline cost | 99% over 30 days | Run cost ≤ $25 and cost per thousand outputs ≤ $2 by default | ML platform |

`page` means immediate operator attention; `ticket` means remediation within the next business
cycle; `info` is diagnostic. Destination minimum severity prevents lower-priority events from
being sent to high-interruption channels.

## Alert routing

Destinations and policies are configured without code changes. `log` destinations emit structured
JSON to the process logger. `webhook` destinations emit the normalized event body, while `slack`
destinations produce a concise human-readable message. Both resolve their URL from the configured
environment variable; URLs and tokens never belong in YAML.

The operator path queries the configured warehouse signal marts directly:

```bash
make forecast-alerts-evaluate DRY_RUN=true
make forecast-alerts-evaluate
```

`DRY_RUN=true` evaluates live signals and prints the alert events without routing them. The second
command routes events according to `vertex/config/monitoring.yaml`.

For deterministic incident replay without BigQuery access, export the relevant marts as JSON arrays
and run:

```bash
python scripts/evaluate_monitoring_alerts.py \
  --source json \
  --feature-completeness-json /tmp/feature-completeness.json \
  --data-drift-json /tmp/data-drift.json \
  --pipeline-cost-json /tmp/pipeline-cost.json \
  --publication-freshness-json /tmp/publication-freshness.json \
  --prediction-coverage-json /tmp/prediction-coverage.json \
  --pipeline-health-json /tmp/pipeline-health.json \
  --realized-calibration-json /tmp/realized-calibration.json \
  --dry-run
```

The repository routes ticket/page policies to `forecasting_ops_slack`. Local non-dry-run evaluation
requires `FORECAST_SLACK_WEBHOOK_URL`; hosted evaluation receives that variable from Secret Manager.

Publication freshness follows the declared ingestion mode. Continuous sources compare the latest
publication timestamp with the configured wall-clock threshold. When every registered source is
`static_demo`, the mart reports `freshness_status = 'static_demo'` and does not page merely because
the intentionally fixed dataset has not produced another publication. Missing or failed source
ingestion and other pipeline-health signals remain independently alertable.

## Cloud-managed failure alert

Terraform includes an opt-in `monitoring-alerts` module. It creates an error-log metric and a Cloud
Monitoring policy covering Vertex custom jobs, Cloud Run jobs, and Cloud Scheduler jobs. It also
promotes structured SLO events from the hosted evaluator into the configured channels. The
`monitoring-runner` module creates an authenticated, hourly Cloud Scheduler → Cloud Run Job path
that rebuilds the marts and evaluates alerts. Both are disabled by default. Enable them only after
supplying channel IDs, an immutable production image digest, and the ID of an existing Secret
Manager secret whose latest version contains the Slack incoming-webhook URL:

```hcl
enable_monitoring_alerts = true
monitoring_notification_channel_ids = [
  "projects/my-project/notificationChannels/1234567890",
]
enable_monitoring_runner = true
monitoring_runner_image = "us-central1-docker.pkg.dev/my-project/vertex/ml-pipeline@sha256:..."
monitoring_slack_webhook_secret_id = "forecast-slack-webhook"
```

Create the secret container and add the webhook through stdin so it never appears in shell history:

```bash
gcloud secrets create forecast-slack-webhook \
  --project=my-project --replication-policy=automatic
gcloud secrets versions add forecast-slack-webhook \
  --project=my-project --data-file=-
```

Paste the webhook URL, press Enter, then send EOF (`Ctrl-D`). Terraform grants only the monitoring
job service account access to the secret. Do not put the URL in `.tfvars`, YAML, or GitHub variables.

## Runbooks

- **Stale or missing publication:** inspect `forecast_pipeline_health`, confirm the latest draft
  crossed all gates, then follow `docs/forecast_operations.md`. Never publish around a failed gate.
- **Low coverage:** compare expected and distinct output counts, inspect eligibility snapshot and
  excluded series, then retry the failed scoring stage with the same run identity.
- **Eligibility evidence:** for `missing_eligibility_evidence`, confirm the run predates the ledger
  or rerun the scheduled pipeline. For snapshot, accounting, exclusion, or eligible-prediction
  mismatches, do not publish; compare `forecast_runs`, `forecast_eligibility_decisions`, and
  `forecast_outputs` by `forecast_run_id` and correct the producing stage.
- **Pipeline failure:** use the contract and run IDs in the alert to inspect Prefect and GCP logs;
  remediate the failed stage before retrying.
- **Source alert:** validate the latest immutable ingestion record and source policy before rerunning
  downstream features.
- **Feature completeness:** inspect the named feature relation at `feature_date`, distinguish
  expected out-of-scope rows from genuine null/entity loss, and stop scoring until the feature
  contract is restored. Use `scope_column`/`scope_value` for intentional partitions.
- **Realized calibration:** inspect `forecast_realized_calibration` by contract and horizon. For
  `under_coverage`, review interval calibration residuals and recent demand regimes. For
  `material_bias`, compare median errors with actual demand and retraining/backtest evidence before
  promoting or recalibrating a model. Do not page on `insufficient_actuals`.
- **Data drift:** inspect `forecast_data_drift` by source model and metric. Confirm both comparison
  windows represent equivalent operational populations, then investigate upstream policy changes,
  promotions, assortment changes, or source defects. Backtest before retraining or promotion; do
  not alert on `insufficient_observations`.
- **Pipeline cost:** inspect `forecast_pipeline_cost` and its `cost_scope_key`. Correct missing
  contract, run, stage, or environment labels before cost analysis. For budget or anomaly tickets,
  compare service-level events, bytes/slots, output cardinality, and historical runs before changing
  schedules or compute. `cost_data_unavailable` means collection must be wired, not that spend is zero.

Repository monitoring signals are complete. Production activation is complete only after applying
the opt-in runner and alert resources and recording a witnessed Slack notification and recovery.
