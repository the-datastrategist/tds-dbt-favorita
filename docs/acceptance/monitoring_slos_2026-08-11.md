# Monitoring and SLO acceptance — 2026-08-11

The publication-freshness, prediction-coverage, alert-contract, and infrastructure slice passed
local validation and live BigQuery acceptance in the `tds-favorita` development environment.

## Live signal evidence

The monitoring selector built five views and completed its selected test set successfully:

```text
PASS=44 WARN=0 ERROR=0 SKIP=0 NO-OP=0 REUSED=0 TOTAL=44
```

The latest monitored publication returned:

| Signal | Result |
|---|---|
| Forecast contract | `favorita_store_daily_demand_h7_hierarchical_publication` |
| Freshness status | `fresh` |
| Publication age | `16 minutes` |
| Alerting | `false` |

Prediction coverage returned healthy results for both available publication runs:

| Forecast contract | Forecast run ID | Coverage | Status | Alerting |
|---|---|---:|---|---|
| `favorita_store_daily_demand_h7_hierarchical_publication` | `c9529665...` | `1.0` | `healthy` | `false` |
| `store_daily_demand_h7_publication` | `5f0d24...` | `1.0` | `healthy` | `false` |

The abbreviated run IDs are sufficient to distinguish the accepted runs; the authoritative full
IDs remain in the warehouse views.

## Alert and infrastructure validation

- The versioned YAML alert/SLO contract passed validation and deterministic hashing tests.
- Synthetic stale, low-coverage, and unhealthy-pipeline signals produced the expected severities.
- Structured-log routing and environment-indirected webhook routing passed unit tests.
- Terraform formatting and validation passed for both development and production environments
  with alert resources disabled by default.
- The opt-in infrastructure defines a log-based failure metric and a Cloud Monitoring alert policy;
  notification channel IDs remain environment inputs rather than repository secrets.

## Regression validation

The full Python suite passed:

```text
361 passed, 7 warnings
TOTAL coverage: 77.12% (required: 75%)
```

dbt parsing, monitoring compilation, schema tests, data tests, and the new coverage/freshness unit
tests passed. Targeted formatting, import sorting, linting, and type checking also passed.

## Defect corrected during acceptance

The first freshness query treated every forecast contract as publication-monitored. That produced
a false missing-publication alert for an older draft-only contract. Publication paging is now
explicitly opt-in through `publication_monitored_contracts`; prediction coverage continues to
evaluate every run with declared expected output. The final freshness result contains only the
hierarchical delivery contract and reports it as fresh.

## Remaining production activation

This acceptance proves the repository implementation and live warehouse signals. Production alert
delivery still requires an enabled Terraform plan/apply with real notification channel IDs, a
hosted schedule for signal evaluation, and a witnessed notification delivery. Feature
completeness, realized calibration, target/feature drift, and cost monitoring remain separate
increments in the broader monitoring spec.
