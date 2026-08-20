# ForecastLab production acceptance — 2026-08-19

## Result

**Accepted for read-only use.** The same-origin ForecastLab application and warehouse-backed API
are deployed behind IAP. Lifecycle mutations and lifecycle roles remain disabled. This acceptance
does not authorize the separate controlled-mutation phase.

## Deployment evidence

| Field | Accepted value |
|---|---|
| Project | `tds-favorita` |
| Region | `us-central1` |
| Cloud Run service | `forecast-retrieval-api` |
| Revision | `forecast-retrieval-api-00006-2pp` |
| Image | `us-central1-docker.pkg.dev/tds-favorita/vertex/tds-favorita@sha256:b8f3b2636161160dfeb2caa3eeda26b53f312475cc72802cfaa64b93a0dc0b9e` |
| IAP access | One named user; no public principal |
| Runtime service account | `forecast-retrieval-api@tds-favorita.iam.gserviceaccount.com` |

The runtime environment reported `FORECAST_API_MUTATIONS_ENABLED=false`,
`FORECAST_API_AUTHORIZATION_ENABLED=true`, and an empty lifecycle-role map. The runtime identity
has `roles/bigquery.jobUser` at project scope and `roles/bigquery.dataViewer` on `favorita`.

## Access and application evidence

- Anonymous requests to `/`, `/overview`, `/experiments`, and `/forecasts` returned HTTP 302 to
  Google OAuth through the configured custom IAP client.
- The IAP policy grants `roles/iap.httpsResourceAccessor` to one named user. No `allUsers` or
  `allAuthenticatedUsers` member is present.
- The IAP service agent has `roles/run.invoker` on the Cloud Run service.
- The authorized operator completed Google sign-in and confirmed that ForecastLab loads in the
  browser.
- Before IAP activation, the same immutable revision returned 14 experiment runs, seven experiment
  models, six operations runs, one published forecast run, 55 forecast entities, and horizon 7.
- `/v1/capabilities` reported `mutationsEnabled: false` and the viewer role.
- Repository browser tests cover direct refreshes for Forecasts, Experiments, Accuracy, and
  Operations in API and public-demo routing modes.

## Terraform reconciliation

The existing Cloud Run service, service account, BigQuery grants, IAP identity and policies,
monitoring job, scheduler, Slack-secret access, and enabled project APIs were adopted into the
populated development remote state in `tds-favorita-terraform-state`. Both Cloud Run resources keep
deletion protection enabled. The normal post-reconciliation plan completed with:

```text
No changes. Your infrastructure matches the configuration.
```

The local environment configuration pins the accepted digest, enables IAP for the single named
member, leaves lifecycle roles empty, and keeps mutations disabled.

## Rollback

Rollback triggers are a failed authorized sign-in, OAuth redirect loops, sustained server errors,
or loss of warehouse-read capability. Roll back the service to image digest
`sha256:cabf3fe04f4ab47d2107dcc7f50d416aa2b54cee05f7bbb82ce9c4a75282994c`, preserve private IAM,
and disable IAP only if the OAuth configuration itself prevents recovery. Do not enable mutations
as part of rollback.
