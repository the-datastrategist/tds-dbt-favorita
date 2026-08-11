# Forecast Retrieval API

The Forecast Retrieval API provides read-only access to complete immutable publication versions.
It never reads partially visible pipeline state and never combines rows from different
run/version/destination tuples.

## Run locally

Application Default Credentials need BigQuery job and read access to the dbt dataset.

```bash
make forecast-api-local
```

OpenAPI is available at `http://localhost:8080/docs` and
`http://localhost:8080/openapi.json`. Run focused tests with `make forecast-api-test`.

## Authentication

The Terraform service is private by default. Cloud Run validates the caller's Google-signed OIDC
token and grants invocation only to `forecast_api_invoker_members`. The runtime service account has
only `roles/bigquery.jobUser` at project scope and `roles/bigquery.dataViewer` on the dbt dataset.

Invoke a deployed service with an identity token:

```bash
curl --fail --silent \
  --header "Authorization: Bearer $(gcloud auth print-identity-token)" \
  "${FORECAST_API_URL}/v1/forecasts/current?contract_name=<contract>&destination=canonical_bigquery"
```

Do not grant `allUsers` or `allAuthenticatedUsers` in production.

## Endpoints

### Latest delivered version

```text
GET /v1/forecasts/current?contract_name=...&destination=...
```

`current` resolves one latest completely delivered version from `forecast_delivery_current`, then
queries only that run/version/destination. It does not assemble an answer from independently latest
entity rows.

### Explicit immutable version

```text
GET /v1/forecasts/runs/{forecast_run_id}?publication_version=3&destination=...
```

Use this endpoint for reproducible consumers. The API compares the persisted publication row count
with the delivery contract before returning any rows. A mismatch returns `409` and no forecast
payload.

Both endpoints accept:

| Parameter | Meaning |
|---|---|
| `entity_key` | Exact non-empty JSON object, canonicalized before lookup |
| `target_start`, `target_end` | Inclusive ISO date range |
| `horizon` | Repeatable positive integer filter |
| `limit` | Page size from 1 to 500; default 100 |
| `page_token` | Opaque keyset cursor returned by the prior response |

Rows use deterministic ordering by entity key, target date, horizon, and publication ID. Responses
include contract name/hash, run ID, version, destination, delivery status, configured publication
row count, quantiles, hierarchy/reconciliation lineage, and model/feature/code provenance.

## Errors

Errors use a stable `code` and human-readable `message`:

| Status | Code | Meaning |
|---|---|---|
| 400 | `invalid_page_token` | Cursor is malformed or has an incompatible shape |
| 404 | `publication_not_found` | No matching current or explicit publication scope exists |
| 409 | `incomplete_publication` | Persisted rows do not match the publication contract |
| 422 | `validation_error` | Required parameters or types are invalid |
| 422 | `invalid_entity_key` | Entity key is not a non-empty JSON object |
| 422 | `invalid_date_range` | Start date follows end date |
| 500 | `internal_error` | Retrieval failed without exposing warehouse internals |

## Deploy

Set the opt-in Terraform variables with an immutable image digest:

```hcl
enable_forecast_api          = true
forecast_api_image           = "us-central1-docker.pkg.dev/PROJECT/vertex/ml-pipeline@sha256:..."
forecast_api_invoker_members = ["group:forecast-consumers@example.com"]
```

Apply the selected environment and use its `forecast_api_url` output. Roll back by deploying the
prior immutable digest. Disabling the module removes the service, service account, and grants; it
does not modify forecast data.

The reference development environment passed live private Cloud Run, IAM, BigQuery retrieval,
filter, pagination, provenance, and structured-error acceptance on 2026-08-11. See
[Forecast Retrieval API acceptance](acceptance/forecast_retrieval_api_2026-08-11.md).
