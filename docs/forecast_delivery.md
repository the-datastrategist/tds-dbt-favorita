# Forecast delivery events

Use this runbook after an immutable publication version has been written or exported. Delivery
outcomes never update `forecast_publications`; they are appended to `forecast_delivery_events` and
resolved through `forecast_delivery_current`.

## Contract

The delivery identity is `(forecast_run_id, publication_version, destination)`. Every command also
requires an actor and a stable idempotency key. The operator validates that the selected publication
contains exactly the expected canonical output count before writing an event.

```text
no event -> pending -> delivered
                    -> failed -> pending (next attempt) -> delivered
                    -> abandoned
           failed  -> abandoned
```

`delivered` and `abandoned` are terminal. Retrying the same command with the same idempotency key
returns the existing event. Reusing a key for different semantics fails closed.

## Commands

Start delivery after publication or export:

```bash
make forecast-delivery-start \
  FORECAST_RUN_ID=<run-id> VERSION=3 DESTINATION=canonical_bigquery \
  ACTOR=delivery-service IDEMPOTENCY_KEY=<stable-key>
```

Record a failure and start the next attempt:

```bash
make forecast-delivery-fail \
  FORECAST_RUN_ID=<run-id> VERSION=3 DESTINATION=canonical_bigquery \
  ACTOR=delivery-service IDEMPOTENCY_KEY=<stable-key> \
  ERROR_CODE=DOWNSTREAM_503 ERROR_MESSAGE='Consumer unavailable'

make forecast-delivery-retry \
  FORECAST_RUN_ID=<run-id> VERSION=3 DESTINATION=canonical_bigquery \
  ACTOR=delivery-service IDEMPOTENCY_KEY=<new-stable-key>
```

Confirm the consumer-visible artifact:

```bash
make forecast-delivery-confirm \
  FORECAST_RUN_ID=<run-id> VERSION=3 DESTINATION=canonical_bigquery \
  ACTOR=delivery-service IDEMPOTENCY_KEY=<stable-key> \
  DELIVERY_REFERENCE='gs://bucket/path/run-v3-*.parquet'
```

Use `forecast-delivery-abandon` only when operations has decided no further attempt should occur.
The abandoned event retains the failed or pending history.

## Publication events and consumption

Successful publish, revision, and rollback operations emit one version-level event to
`forecast_publication_events`. Consumers can use `forecast_publication_events_audit` for polling or
as the source for a webhook adapter. Payloads contain the contract name/hash, run, version,
destination, row count, event time, and prior version when applicable.

Use these stable views:

| View | Purpose |
|---|---|
| `forecast_publication_events_audit` | Publish/revise/rollback integration events |
| `forecast_delivery_current` | Latest state for every immutable run/version/destination |
| `forecast_delivery_health` | Latest version per contract/destination with failure and overdue alerts |

Delivery failure does not remove or mutate a publication. Inspect event history, remediate the
downstream fault, and use a new retry idempotency key. A later delivered event makes current health
non-alerting while the earlier failure remains auditable.

The central monitoring evaluator reads `forecast_delivery_health`. Any status other than `healthy`
routes the `forecast_delivery_unhealthy` page policy to the configured operator destination. Use
`make forecast-alerts-evaluate DRY_RUN=true` to inspect alerts without emitting notifications.

## Required access

Operators need BigQuery read access to canonical publications and append access to the two event
tables. Webhook or file delivery credentials remain destination-specific and must not be stored in
the event payload or repository.
