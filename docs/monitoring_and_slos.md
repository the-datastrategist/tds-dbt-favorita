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
- `ml_prediction_accuracy_rolling` remains the existing model-accuracy and drift signal and is run
  with `make selector-accuracy-monitoring`.

For deterministic validation, pass a timestamp to dbt with
`--vars '{monitoring_evaluated_at: "2026-08-05 12:00:00+00"}'`.

## Operating expectations

For this demonstration repository, run ingestion evidence once after loading the immutable raw
snapshot and again only if the snapshot or loader changes. Run pipeline health after every forecast
execution. In a continuously updating deployment, invoke the same evidence writer from every
scheduled or event-driven loader and run the monitoring selector after each load and forecast run.

Alert routing and cloud-managed SLO policies remain future work. Until those are configured,
`is_alerting = true` and non-`healthy` pipeline states are the warehouse-level alert interface.
