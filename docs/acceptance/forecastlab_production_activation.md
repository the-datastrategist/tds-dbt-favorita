# ForecastLab production activation

ForecastLab activation is intentionally split into two independent gates. Phase 1 proves the
same-origin frontend and API with IAP and warehouse reads while lifecycle mutations and lifecycle
roles remain disabled. Phase 2 is a later, controlled mutation exercise. Passing the read-only gate
must never be interpreted as authorization to enable writes.

## Phase 1 — read-only IAP acceptance

Do not mark this phase accepted until an immutable merged image is deployed and the automated and
manual evidence below is captured.

## Deployment inputs

| Field | Accepted value |
|---|---|
| Project | `tds-favorita` |
| Region | `us-central1` |
| Cloud Run service | `forecast-retrieval-api` |
| Revision | `forecast-retrieval-api-00006-2pp` |
| Image digest | `sha256:b8f3b2636161160dfeb2caa3eeda26b53f312475cc72802cfaa64b93a0dc0b9e` |
| IAP access members | One named user; no public principal |

## Required Terraform configuration

```hcl
enable_forecast_api            = true
enable_forecast_api_mutations  = false
enable_forecastlab_iap         = true
forecastlab_iap_access_members = ["user:analyst@example.com"]
forecastlab_lifecycle_role_members = {}
forecast_api_image             = "us-central1-docker.pkg.dev/PROJECT/vertex/ml-pipeline@sha256:..."
```

The plan must enable IAP on the service, grant `roles/run.invoker` to the IAP service agent, and
grant `roles/iap.httpsResourceAccessor` only to the declared members. It must not introduce
`allUsers` or `allAuthenticatedUsers`, lifecycle roles, BigQuery editor access, or a mutable image
tag.

### Repeatable plan gate

Create, but do not apply, the development plan and run the fail-closed gate:

```bash
terraform -chdir=terraform/environments/dev plan -out=tfplan
make forecastlab-readonly-plan-check
```

The command rejects destructive changes, public principals, mutable images, disabled IAP,
lifecycle roles, mutation mode, missing IAP users, missing IAP invocation, and BigQuery editor
access. It writes sanitized evidence to `artifacts/forecastlab-acceptance/plan.json`; the raw plan
must not be committed because it can contain deployment configuration.

After an approved apply, an authorized operator can capture deployment and API evidence:

```bash
make forecastlab-readonly-live-check \
  PROJECT=PROJECT_ID \
  REGION=us-central1 \
  SERVICE=forecast-retrieval-api \
  URL=https://SERVICE_URL \
  MANUAL_BROWSER=true
```

The operator running this command needs an authenticated `gcloud` session and IAP access. The
generated `live.json` contains revision and digest metadata plus the anonymous-denial result; it
excludes identities, tokens, and response bodies. `MANUAL_BROWSER=true` is required when IAP uses
only a human web OAuth client. A separately allowlisted programmatic client or service-account
identity can instead supply `IAP_CLIENT_ID` to automate the authenticated API probes.

## Browser and API evidence

- An unauthorized private-browser session is denied or redirected to sign-in.
- An authorized account loads `/overview`, `/experiments`, `/accuracy`, `/operations`, and a direct
  refresh of `/forecasts`.
- The environment label reads `Authenticated production data`.
- `/v1/forecasts/options?run_id=...` returns only entities, models, and horizons from that run.
- Forecast filtering, target-date bounds, and opaque pagination return immutable delivered rows.
- P10, P50, and P90 remain ordered and the provenance drawer contains the contract, model,
  calibration, reconciliation, hierarchy, feature-availability, code, and publication identifiers.
- A controlled invalid request returns a structured error and `X-Request-ID`; the same ID is found
  in Cloud Run logs.
- GitHub Pages still identifies itself as `Synthetic public demo` and makes no production API
  request.
- `/v1/experiments` returns persisted rolling origins, horizons, segments, feature evidence, and
  comparable confidence evidence.
- `/v1/operations` exposes lifecycle, exception, delivery, and FVA evidence without leaking comments
  or unrestricted logs.
- `/v1/capabilities` reports `mutationsEnabled: false` and no lifecycle action is attempted.
- The automated live check passes and its sanitized evidence is attached to the acceptance record.
- An authorized interactive browser session completes IAP sign-in and the direct-route checks.
  The bearer-token probe does not replace this browser-session evidence.

### Phase 1 result

**Accepted on 2026-08-19 for read-only use.** The immutable revision is IAP-protected, anonymous
browser requests redirect to Google sign-in, the authorized operator completed interactive sign-in,
and the warehouse-backed ForecastLab application loads. Mutations remain disabled, lifecycle roles
remain empty, the runtime keeps dataset viewer access, and the normal Terraform plan reports no
changes after state reconciliation. See the
[production acceptance evidence](forecastlab_production_2026-08-19.md).

## Phase 2 — controlled lifecycle mutation acceptance

This phase begins only after Phase 1 is accepted and a separate change is approved. Use a controlled
environment, set `enable_forecast_api_mutations = true`, and assign named planner, approver, and
publisher roles. Record evidence that:

- a planner can propose an override but cannot approve or publish;
- an approver can approve or reject but cannot publish;
- a publisher can complete an idempotent publication, supersession, and rollback exercise;
- conflicting retries fail without rewriting append-only history;
- the persisted actor equals the IAP identity and ignores any actor supplied by the browser; and
- rollback to the accepted read-only image and configuration is tested.

Mutation acceptance has its own rollback decision and must not overwrite the Phase 1 evidence.
