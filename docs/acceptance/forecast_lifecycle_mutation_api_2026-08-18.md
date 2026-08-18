# Forecast lifecycle mutation API acceptance — 2026-08-18

The append-only override, approval, and publication endpoints passed local contract acceptance.
This evidence covers repository implementation and opt-in infrastructure configuration; production
mutation activation remains intentionally separate.

## Accepted endpoints

| Endpoint | Accepted behavior |
|----------|-------------------|
| `POST /v1/overrides` | Appends one nonnegative planner override without changing canonical output |
| `POST /v1/forecast-runs/{forecast_run_id}/approve` | Freezes one complete approval set using the latest override per output |
| `POST /v1/forecast-runs/{forecast_run_id}/publish` | Publishes one explicitly named, complete approval set and emits `forecast.published` |

All mutations require actor and idempotency metadata. Exact retries return the persisted logical
result. Conflicting idempotency keys, incomplete approval sets, and non-monotonic publication
versions fail closed with structured errors.

## Validation results

- Focused API and forecast-operation suite: `18 passed`.
- Complete unit suite: `385 passed`, `7 deselected`.
- Coverage: `75.82%`, above the 75% gate.
- Python formatting, import ordering, targeted lint, and whitespace checks passed.
- Terraform development and production configurations validated successfully.

## Deployment boundary

Lifecycle mutations are disabled by default through `FORECAST_API_MUTATIONS_ENABLED=false` and
`enable_forecast_api_mutations=false`. The default runtime retains dataset-level
`roles/bigquery.dataViewer`. Enabling mutations changes that grant to
`roles/bigquery.dataEditor`, so `forecast_api_invoker_members` must contain only trusted operators.

The existing [retrieval acceptance](forecast_retrieval_api_2026-08-11.md) remains the live Cloud Run
evidence. Mark mutation delivery live accepted only after deploying an immutable image, applying
the operator-only IAM configuration, and witnessing idempotent override, approval, and publication
requests against a controlled forecast run.
