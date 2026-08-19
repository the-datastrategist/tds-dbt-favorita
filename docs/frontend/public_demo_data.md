# ForecastLab public demo data contract

- **Status:** Approved
- **Approved:** 2026-08-18
- **Applies to:** Public GitHub Pages fixture builds

## Decision

The public ForecastLab demo uses the deterministic synthetic `forecastlab_demo_v1` model-evidence
fixture and `forecastlab_forecasts_demo_v1` canonical-forecast fixture. Neither is an extract,
anonymization, or sample of production data, and neither redistributes raw Favorita competition
rows. The GitHub Pages build is read-only and makes no authenticated or cloud data request.

## Demonstration population

The packaged fixture release models:

- 2 fictional store series in 2 fictional hierarchy nodes;
- 2 fictional publication runs, including published and superseded lifecycle states;
- actuals and seven future target dates on a fixed demonstration calendar;
- 3 fictional model candidates plus seasonal-naive and moving-average baselines;
- horizons 1 through 7 with P10, P50, and P90 predictions;
- one controlled published adjustment and exception state; and
- synthetic contract, model, calibration, reconciliation, hierarchy, feature, cutoff, code, and
  publication provenance.

All identifiers use a `demo_` prefix. Values and outcomes are generated specifically for the demo;
they must not be copied from live warehouse rows.

## Approved public fields

The fixture may expose only these information classes:

| Class | Examples |
|---|---|
| Synthetic identity | Demo series, region, model, run, contract, and publication identifiers |
| Forecast values | Synthetic actuals, P10/P50/P90 predictions, origins, target dates, and horizons |
| Evaluation | WAPE, MAE, RMSE, bias, coverage, interval width, and baseline improvement |
| Methodology | Model family aliases, forecast strategy, fallback reason, confidence, and feature-group names |
| Lifecycle | Synthetic champion, candidate, draft, approved, published, and superseded states |
| Operations | Synthetic freshness, coverage, calibration, drift, cost-band, duration, and alert states |
| Provenance | Fixture version, generator version, synthetic code SHA, and documentation links |

Synthetic cost values must be clearly labeled and must not imply actual cloud spend.

## Prohibited information

The public artifact must not contain:

- real customer, employee, operator, approver, or service-account identity;
- raw Favorita or other operational source rows and source-system identifiers;
- real GCP project, dataset, table, bucket, artifact, Cloud Run, Vertex, or Prefect identifiers;
- production run UUIDs, publication IDs, model artifact URIs, code SHAs, or exception payloads;
- comments, free text, email addresses, IP addresses, access tokens, credentials, or secrets;
- environment variables, private endpoints, internal repository paths, or stack traces;
- actual billing amounts, budgets, account allocation labels, or client commercial information.

## Release controls

Every public fixture release must:

1. Validate against an explicit allowlisted schema.
2. Require `demo_` prefixes for every identifier.
3. Include `dataset_kind: synthetic`, `fixture_version`, and `generated_at` metadata.
4. Fail scanning on credentials, private keys, JWT-like values, email addresses, `gs://` URIs,
   cloud resource URLs, and known production identifiers.
5. Pass a manual diff review confirming that every value is synthetic and presentation-safe.
6. Build and run with browser networking disabled except for same-origin static assets.

This contract is the approval boundary. Adding a field or switching to a transformed real dataset
requires a documented review before publication.
