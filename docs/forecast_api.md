# Forecast Operations API

The Forecast Operations API provides read access to complete immutable publication versions and
optional append-only lifecycle mutations. Retrieval never reads partially visible pipeline state
or combines rows from different run/version/destination tuples. Mutations are disabled by default.

## Run locally

Application Default Credentials need BigQuery job and read access to the dbt dataset.

```bash
make forecast-api-local
```

OpenAPI is available at `http://localhost:8080/docs` and
`http://localhost:8080/openapi.json`. Run focused tests with `make forecast-api-test`.

## Authentication

The Terraform service is private by default. Cloud Run validates the caller's Google-signed OIDC
token and grants invocation only to `forecast_api_invoker_members`. In read-only mode, the runtime
service account has `roles/bigquery.jobUser` at project scope and `roles/bigquery.dataViewer` on the
dbt dataset. Enabling lifecycle mutations changes the dataset role to
`roles/bigquery.dataEditor`; configure only trusted operators as invokers in that mode.

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

### Lifecycle mutations

Lifecycle mutations are append-only and require a non-empty actor and caller-generated idempotency
key. Retries must reuse the exact request. Reusing a key or publication version with different
content returns `409`.

```text
POST /v1/overrides
POST /v1/forecast-runs/{forecast_run_id}/approve
POST /v1/forecast-runs/{forecast_run_id}/publish
```

Override request:

```json
{
  "forecast_run_id": "run-2026-08-18",
  "forecast_output_id": "output-id",
  "override_value": 42.5,
  "reason_code": "planner_context",
  "comment": "Local promotion extended",
  "actor": "planner@example.com",
  "idempotency_key": "override-run-2026-08-18-output-id"
}
```

Approval selects the latest persisted override for each output and freezes one complete decision
set under its idempotency key. Publication must name that exact approval key:

```json
{
  "approval_idempotency_key": "approval-run-2026-08-18",
  "publication_version": 2,
  "destination": "canonical_bigquery",
  "actor": "publisher@example.com",
  "idempotency_key": "publication-run-2026-08-18-v2"
}
```

Publication rejects missing or incomplete approval sets and non-monotonic versions. Successful
publication appends a version-level `forecast.published` event and, when configured, attempts a
signed outbound webhook. The response reports `webhook_delivery_status` and
`webhook_delivery_event_id`; a delivery failure is recorded independently and does not undo the
publication. See [Forecast delivery events](forecast_delivery.md) for receiver verification and
retry semantics.

## Errors

Errors use a stable `code` and human-readable `message`:

| Status | Code | Meaning |
|---|---|---|
| 400 | `invalid_page_token` | Cursor is malformed or has an incompatible shape |
| 404 | `publication_not_found` | No matching current or explicit publication scope exists |
| 409 | `incomplete_publication` | Persisted rows do not match the publication contract |
| 409 | `mutation_conflict` | Idempotency, approval-set, or publication-version state conflicts |
| 422 | `validation_error` | Required parameters or types are invalid |
| 422 | `invalid_mutation` | A lifecycle mutation violates its record contract |
| 422 | `invalid_entity_key` | Entity key is not a non-empty JSON object |
| 422 | `invalid_date_range` | Start date follows end date |
| 403 | `mutations_disabled` | This deployment has not enabled lifecycle writes |
| 404 | `mutation_target_not_found` | The requested run, output, or approval set does not exist |
| 500 | `internal_error` | The request failed without exposing warehouse internals |

## Deploy

Set the opt-in Terraform variables with an immutable image digest:

```hcl
enable_forecast_api          = true
enable_forecast_api_mutations = false
forecast_api_image           = "us-central1-docker.pkg.dev/PROJECT/vertex/ml-pipeline@sha256:..."
forecast_api_invoker_members = ["group:forecast-consumers@example.com"]
```

Apply the selected environment and use its `forecast_api_url` output. Roll back by deploying the
prior immutable digest. Disabling the module removes the service, service account, and grants; it
does not modify forecast data.

To activate mutations, set `enable_forecast_api_mutations = true` and replace consumer-oriented
invoker membership with an operator-only group before applying. Leaving the flag false preserves
the previously accepted read-only service and least-privilege dataset reader role.

Outbound delivery is opt-in and requires mutations. Store the destination URL and signing secret
in separate Secret Manager secrets, then configure:

```hcl
enable_publication_webhook            = true
publication_webhook_url_secret_id     = "forecast-publication-webhook-url"
publication_webhook_signing_secret_id = "forecast-publication-webhook-signing-secret"
publication_webhook_name              = "planning"
```

The module grants the runtime identity access only to those two secrets. The URL must use HTTPS and
must not contain embedded credentials. Disable the flag to stop outbound attempts without changing
publication history.

The reference development environment passed live private Cloud Run, IAM, BigQuery retrieval,
filter, pagination, provenance, and structured-error acceptance on 2026-08-11. See
[Forecast Retrieval API acceptance](acceptance/forecast_retrieval_api_2026-08-11.md). The mutation
routes passed [local lifecycle API acceptance](acceptance/forecast_lifecycle_mutation_api_2026-08-18.md)
and remain disabled in production pending controlled activation.
