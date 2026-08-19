# ForecastLab production activation

This checklist records the remaining live acceptance for the same-origin ForecastLab frontend and
read-only API. Do not mark it accepted until an immutable merged image is deployed and all evidence
below is captured.

## Deployment inputs

| Field | Accepted value |
|---|---|
| Project | Pending |
| Region | Pending |
| Cloud Run service | Pending |
| Revision | Pending |
| Image digest | Pending |
| IAP access members | Pending |

## Required Terraform configuration

```hcl
enable_forecast_api            = true
enable_forecast_api_mutations  = false
enable_forecastlab_iap         = true
forecastlab_iap_access_members = ["user:analyst@example.com"]
forecast_api_image             = "us-central1-docker.pkg.dev/PROJECT/vertex/ml-pipeline@sha256:..."
```

The plan must enable IAP on the service, grant `roles/run.invoker` to the IAP service agent, and
grant `roles/iap.httpsResourceAccessor` only to the declared members. It must not introduce
`allUsers` or `allAuthenticatedUsers`.

## Browser and API evidence

- An unauthorized private-browser session is denied or redirected to sign-in.
- An authorized account loads `/overview`, `/experiments`, and a direct refresh of `/forecasts`.
- The environment label reads `Authenticated production data`.
- `/v1/forecasts/options?run_id=...` returns only entities, models, and horizons from that run.
- Forecast filtering, target-date bounds, and opaque pagination return immutable delivered rows.
- P10, P50, and P90 remain ordered and the provenance drawer contains the contract, model,
  calibration, reconciliation, hierarchy, feature-availability, code, and publication identifiers.
- A controlled invalid request returns a structured error and `X-Request-ID`; the same ID is found
  in Cloud Run logs.
- GitHub Pages still identifies itself as `Synthetic public demo` and makes no production API
  request.

## Result

**Pending live deployment and acceptance.** Local unit, browser, production build, API contract,
Terraform format, and Terraform validation gates pass. Replace this result only after recording
the immutable revision and observed evidence above.
