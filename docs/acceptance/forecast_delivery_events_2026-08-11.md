# Forecast delivery-event acceptance — 2026-08-11

The append-only publication-event and delivery-confirmation contracts passed live acceptance in
`tds-favorita.favorita` using forecast run
`c9529665c1a5ec945e799272e1f77d8da9b645732d741e6b88e5c1e79f6d3b3f`, publication version 3,
and destination `canonical_bigquery`.

## Results

- Additive DDL created `forecast_publication_events` and `forecast_delivery_events`.
- An idempotent rollback replay emitted one `forecast.rolled_back` event with row count 55 and
  publication event ID `8d39fc3d339753eb13f46989c951167f4c8e78c4928ef512ca9f32c0528b87d6`.
- Delivery history contains exactly four transitions: pending attempt 1, failed attempt 1,
  pending attempt 2, and delivered attempt 2.
- The controlled failure retained error code `ACCEPTANCE_503`.
- Delivery confirmation references the accepted five-shard, 55-row Parquet artifact.
- Replaying confirmation returned the existing delivery event
  `cabeae0bd699705141fe4062ff9c1c5814e1b35a168ab0d066ba7ef09ce37f20`.
- `forecast_delivery_current` resolves version 3 to delivered attempt 2.
- `forecast_delivery_health` reports `healthy` and `is_alerting = false` after confirmation.
- The central evaluator routes a controlled failed delivery through the
  `forecast_delivery_unhealthy` page policy; the accepted delivered state produces no delivery
  alert.
- The earlier failed event remains in immutable history.
- `forecast_publications` still contains exactly 165 rows (three complete 55-row versions).

The targeted dbt build completed with `PASS=38 WARN=0 ERROR=0 SKIP=0`, including two unit tests
that prove latest-event resolution and that successful delivery clears a prior failure alert.
The complete Python suite passed 367 tests; the unit coverage run passed 360 tests at 75.71%, above
the required 75% gate. Formatting, import sorting, linting, typing, and diff hygiene also passed.

## Result

**Accepted.** Confirmation, failure, retry, and terminal-state behavior are version-scoped,
idempotent, append-only, and independent of immutable publication rows. An outbound webhook adapter
remains a separate integration increment.
