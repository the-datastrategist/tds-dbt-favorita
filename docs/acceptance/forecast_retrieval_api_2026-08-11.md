# Forecast Retrieval API acceptance — 2026-08-11

The read-only API contract passed local service acceptance against the live
`tds-favorita.favorita` publication views.

## Results

- The current endpoint resolved delivered publication version 3 for run
  `c9529665c1a5ec945e799272e1f77d8da9b645732d741e6b88e5c1e79f6d3b3f`.
- It returned two rows at the requested page size and emitted an opaque next-page token.
- The second page returned HTTP 200 with two different rows, proving live BigQuery keyset
  pagination.
- Seven focused tests passed for current and explicit resolution, canonical entity filters,
  structured validation errors, cursor integrity, bound query parameters, and fail-closed
  publication cardinality.
- The complete unit suite passed 369 tests at 76.31% coverage, above the 75% gate.
- Formatting, import sorting, linting, and API typing passed.
- Terraform formatting and isolated no-backend validation passed for dev and prod.

## Result

**Service contract accepted.** Live Cloud Run deployment, IAM invocation, and hosted OpenAPI smoke
testing remain environment activation work because `enable_forecast_api` defaults to false.
