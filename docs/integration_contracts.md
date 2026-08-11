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
| `forecast_publication_events_audit` | Version-level publish, revise, and rollback events |
| `forecast_delivery_current` | Latest downstream delivery state without mutating publications |
| `forecast_delivery_health` | Delivery failure and overdue-pending monitoring boundary |
| `forecast_eligibility_decisions` | Immutable candidate eligibility/exclusion evidence pinned to a forecast-run snapshot |
| `forecast_realized_calibration` | Matured interval coverage, median bias, interval width, and calibration alert state by contract/horizon |

`published_forecasts_current` is convenient operational state. Reproducible applications should
pin `forecast_run_id`, `publication_version`, and `destination` against
`published_forecasts_by_run`.

Build and validate the contracts with:

```bash
make dbt-run ARGS="--select published_forecasts_current published_forecasts_by_run forecast_publication_audit forecast_overrides_audit"
make dbt-test ARGS="--select published_forecasts_current published_forecasts_by_run forecast_publication_audit forecast_overrides_audit"
```

## Batch export

Export one published run version to Cloud Storage as Parquet or CSV. The destination must contain exactly
one BigQuery shard wildcard.

```bash
make forecast-export \
  FORECAST_RUN_ID=<run-id> \
  VERSION=<publication-version> \
  DESTINATION='gs://favorita-exports/forecasts/<run-id>/*.parquet' \
  FORMAT=parquet
```

The command validates the run ID, publication version, view identifier, URI, and format; it
parameterizes both immutable identifiers and sets `overwrite=false`. A retry therefore cannot silently replace delivered files.
Use a new destination for an intentional re-export.

## Retrieval API

The Cloud Run-ready read-only service exposes one latest delivered version or one explicit
run/version/destination. It validates publication cardinality before returning rows and uses opaque
keyset pagination with parameterized BigQuery filters. See the
[Forecast Retrieval API](forecast_api.md) for endpoints, authentication, errors, and deployment.

## Versioning policy

- Published records and revision lineage are append-only.
- A rollback is a new publication version, not an update to an old one.
- Consumers must not combine rows from different run/version/destination tuples.
- Additive nullable columns are backward-compatible. Renames, removals, semantic changes, or new
  required fields require a versioned view and a documented deprecation window.
- Publication events and delivery confirmation are append-only and version-scoped. The read-only
  retrieval API is implemented; mutation APIs and an outbound webhook adapter remain future
  interfaces over the same records.

See [forecast operations](forecast_operations.md) for override, approval, and rollback commands and
[forecast delivery](forecast_delivery.md) for confirmation, failure, retry, and abandonment.
The Make targets are operator interfaces rather than a public API; callers must have BigQuery/GCS
IAM appropriate to the selected project and destination.
