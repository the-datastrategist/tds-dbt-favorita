# Forecast operations runbook

The scheduled pipeline creates a validated, immutable draft without retraining. Forecast
operations begin at that boundary: a planner may append an adjustment, an approver selects the
statistical or adjusted value, and publication freezes that decision as a versioned record.

## Lifecycle and cadence

```text
draft -> approved -> published -> superseded
```

Daily scoring is independent from weekly or trigger-based challenger retraining and monthly or
trigger-based tuning. Champion promotion remains gated. Operation records are append-only and use
caller-supplied idempotency keys, so retry the exact command with the same key.

## Override one forecast

Identify the canonical `forecast_output_id`, then append the adjustment:

```bash
make forecast-override \
  FORECAST_RUN_ID=<run-id> \
  OUTPUT_ID=<forecast-output-id> \
  VALUE=125.0 \
  ACTOR=planner@example.com \
  IDEMPOTENCY_KEY=override-2026-08-10-store-1-h7 \
  REASON_CODE=local_event \
  COMMENT="Expected store event"
```

The original P50 remains unchanged in `forecast_outputs`. The command writes a separate audited
row to `forecast_overrides`. Approval selects the latest override for each output; outputs without
an override retain their statistical P50.

## Approve and publish

Publish only a complete validated run. Version numbers are explicit and monotonically increasing
for an operational destination:

```bash
make forecast-approve-publish \
  FORECAST_RUN_ID=<run-id> \
  VERSION=1 \
  ACTOR=approver@example.com \
  IDEMPOTENCY_KEY=publish-2026-08-10-v1 \
  REASON_CODE=review_complete \
  COMMENT="Planner review complete" \
  DESTINATION=canonical_bigquery
```

This creates one approval and one publication record per canonical row. Exact retries are no-ops;
a conflicting payload for an existing deterministic ID fails closed.

## Revise a publication

To publish reviewed current values as a revision, use `make forecast-revise` with
`PRIOR_VERSION`, a greater `VERSION`, and the same audit fields shown above. This writes
`supersede` lineage from every complete prior row to its replacement.

## Roll back

Rollback never deletes or reactivates an old version. It republishes the selected complete prior
version under a new version and links every replacement to its source:

```bash
make forecast-rollback \
  FORECAST_RUN_ID=<run-id> \
  PRIOR_VERSION=1 \
  VERSION=3 \
  ACTOR=operator@example.com \
  IDEMPOTENCY_KEY=rollback-2026-08-10-v3 \
  REASON_CODE=bad_revision \
  COMMENT="Restore version 1 values"
```

The command refuses an incomplete source version or a new version that is not greater than the
selected source. `forecast_revisions` preserves prior and replacement publication IDs.

## Recovery rules

- Retry transient failures with the same arguments and idempotency key.
- Correct operator input with a new idempotency key; do not mutate an existing event.
- Never use rollback to change the champion. Model rollback is handled by the model-lifecycle
  command and affects a subsequent forecast run.
- A backfill cannot supersede a newer operational version unless the operator deliberately issues
  a revision with an audit reason.
- Delivery failure does not erase publication. Retry the delivery/export and retain the immutable
  publication version.

Stable consumer views and batch export are documented in
[integration contracts](integration_contracts.md).

These commands are the supported operator boundary today. They are not a public multi-tenant API;
the executing identity must have append access to the forecast-operation tables.
