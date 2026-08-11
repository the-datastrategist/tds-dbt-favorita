# Forecast Retrieval API acceptance — 2026-08-11

The read-only API contract passed local service acceptance and live private Cloud Run acceptance
against the `tds-favorita.favorita` publication views.

## Live deployment

| Field | Accepted value |
|---|---|
| Project | `tds-favorita` |
| Region | `us-central1` |
| Service | `forecast-retrieval-api` |
| Revision | `forecast-retrieval-api-00001-lr9` |
| Runtime identity | `forecast-retrieval-api@tds-favorita.iam.gserviceaccount.com` |
| Image digest | `sha256:b18d4ba3eca66194a089a13c0bd6f88848b93d132705c93f657b5aa07f3ab07a` |

Terraform applied nine additive resources with zero changes or destroys. A subsequent plan using
the persisted development configuration returned `No changes`. The runtime identity has only
project-level `roles/bigquery.jobUser` and dataset-level `roles/bigquery.dataViewer`. Cloud Run IAM
contains one explicit invoker and no `allUsers` or `allAuthenticatedUsers` principal.

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
- Unauthenticated access returned HTTP 403; the configured invoker retrieved OpenAPI and forecast
  responses with HTTP 200.
- The hosted current endpoint resolved the same delivered version 3 and returned the frozen
  publication cardinality of 55 rows.
- Two consecutive two-row pages contained four distinct publication IDs, proving hosted keyset
  pagination without duplicates.
- Explicit run/version retrieval with entity, date, and horizon filters returned only the expected
  `company:all`, `2017-08-23`, horizon-7 row.
- The hosted row retained ordered P10/P50/P90 values and complete hierarchy, reconciliation, model,
  feature, and code provenance.
- Malformed cursor, absent publication version, and invalid date range requests returned structured
  `400 invalid_page_token`, `404 publication_not_found`, and `422 invalid_date_range` responses.
  The generic structured `500 internal_error` path remains covered by the focused service tests; no
  live warehouse failure was induced merely to exercise it.

## Result

**Live service accepted.** The development environment now runs the immutable, private retrieval
service and retains the opt-in values in its ignored local `terraform.tfvars`. Other environments
remain disabled by default until they provide an immutable image and explicit invoker members.
