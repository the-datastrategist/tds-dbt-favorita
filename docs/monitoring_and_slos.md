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

For deterministic validation, pass a timestamp to dbt with
`--vars '{monitoring_evaluated_at: "2026-08-05 12:00:00+00"}'`.

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

`page` means immediate operator attention; `ticket` means remediation within the next business
cycle; `info` is diagnostic. Destination minimum severity prevents lower-priority events from
being sent to high-interruption channels.

## Alert routing

Destinations and policies are configured without code changes. `log` destinations emit structured
JSON to the process logger. `webhook` destinations resolve their URL from the configured environment
variable; URLs and tokens never belong in YAML.

The operator path queries the four warehouse marts directly:

```bash
make forecast-alerts-evaluate DRY_RUN=true
make forecast-alerts-evaluate
```

`DRY_RUN=true` evaluates live signals and prints the alert events without routing them. The second
command routes events according to `vertex/config/monitoring.yaml`.

For deterministic incident replay without BigQuery access, export the three marts as JSON arrays
and run:

```bash
python scripts/evaluate_monitoring_alerts.py \
  --source json \
  --feature-completeness-json /tmp/feature-completeness.json \
  --publication-freshness-json /tmp/publication-freshness.json \
  --prediction-coverage-json /tmp/prediction-coverage.json \
  --pipeline-health-json /tmp/pipeline-health.json \
  --dry-run
```

For hosted routing, schedule the evaluator after the monitoring dbt selector, replace
`operator_log` or add a webhook destination in
`vertex/config/monitoring.yaml`, set its `url_env_var`, and omit `--dry-run`.

## Cloud-managed failure alert

Terraform includes an opt-in `monitoring-alerts` module. It creates an error-log metric and a Cloud
Monitoring policy covering Vertex custom jobs, Cloud Run jobs, and Cloud Scheduler jobs. It also
promotes structured SLO events from the hosted evaluator into the configured channels. The
`monitoring-runner` module creates an authenticated, hourly Cloud Scheduler → Cloud Run Job path
that rebuilds the marts and evaluates alerts. Both are disabled by default. Enable them only after
supplying channel IDs and an immutable production image digest:

```hcl
enable_monitoring_alerts = true
monitoring_notification_channel_ids = [
  "projects/my-project/notificationChannels/1234567890",
]
enable_monitoring_runner = true
monitoring_runner_image = "us-central1-docker.pkg.dev/my-project/vertex/ml-pipeline@sha256:..."
```

## Runbooks

- **Stale or missing publication:** inspect `forecast_pipeline_health`, confirm the latest draft
  crossed all gates, then follow `docs/forecast_operations.md`. Never publish around a failed gate.
- **Low coverage:** compare expected and distinct output counts, inspect eligibility snapshot and
  excluded series, then retry the failed scoring stage with the same run identity.
- **Pipeline failure:** use the contract and run IDs in the alert to inspect Prefect and GCP logs;
  remediate the failed stage before retrying.
- **Source alert:** validate the latest immutable ingestion record and source policy before rerunning
  downstream features.
- **Feature completeness:** inspect the named feature relation at `feature_date`, distinguish
  expected out-of-scope rows from genuine null/entity loss, and stop scoring until the feature
  contract is restored. Use `scope_column`/`scope_value` for intentional partitions.

The next monitoring increment adds realized calibration, feature/target drift, and cost marts.
Production activation requires applying the opt-in runner and alert resources with real channel
IDs, then recording a witnessed notification delivery.
