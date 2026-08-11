# Forecast integration contracts

Downstream consumers should use the stable publication views, never intermediate scoring or stage
tables. Every retrieval and export retains the forecast contract, logical run, entity, origin,
target date, horizon, publication version, and frozen published value.

## Warehouse views

| View | Use |
|---|---|
| `published_forecasts_current` | Latest published value by contract/entity/target/horizon/destination |
| `published_forecasts_by_run` | Reproducible retrieval of an explicit immutable run and version |
| `forecast_publication_audit` | Approval, delivery, and revision lineage |
| `forecast_overrides_audit` | Statistical values, planner adjustments, and approval decisions |

`published_forecasts_current` is convenient operational state. Reproducible applications should
pin `forecast_run_id`, `publication_version`, and `destination` against
`published_forecasts_by_run`.

Build and validate the contracts with:

```bash
make dbt-run ARGS="--select published_forecasts_current published_forecasts_by_run forecast_publication_audit forecast_overrides_audit"
make dbt-test ARGS="--select published_forecasts_current published_forecasts_by_run forecast_publication_audit forecast_overrides_audit"
```

## Batch export

Export one published run to Cloud Storage as Parquet or CSV. The destination must contain exactly
one BigQuery shard wildcard.

```bash
make forecast-export \
  FORECAST_RUN_ID=<run-id> \
  DESTINATION='gs://favorita-exports/forecasts/<run-id>/*.parquet' \
  FORMAT=parquet
```

The command validates the run ID, view identifier, URI, and format; it parameterizes the run
filter and sets `overwrite=false`. A retry therefore cannot silently replace delivered files.
Use a new destination for an intentional re-export.

## Versioning policy

- Published records and revision lineage are append-only.
- A rollback is a new publication version, not an update to an old one.
- Consumers must not combine rows from different run/version/destination tuples.
- Additive nullable columns are backward-compatible. Renames, removals, semantic changes, or new
  required fields require a versioned view and a documented deprecation window.
- The warehouse and export contracts are shipped first. Retrieval and mutation APIs and
  publication webhooks remain future adapters over the same records.

See [forecast operations](forecast_operations.md) for override, approval, and rollback commands.
The Make targets are operator interfaces rather than a public API; callers must have BigQuery/GCS
IAM appropriate to the selected project and destination.
