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
| Publication age | `20 minutes` |
| Alerting | `false` |

Prediction coverage returned healthy results for both available publication runs:

| Forecast contract | Forecast run ID | Coverage | Status | Alerting |
|---|---|---:|---|---|
| `favorita_store_daily_demand_h7_hierarchical_publication` | `c9529665...` | `1.0` | `healthy` | `false` |
| `store_daily_demand_h7_publication` | `5f0d24...` | `1.0` | `healthy` | `false` |

The abbreviated run IDs are sufficient to distinguish the accepted runs; the authoritative full
IDs remain in the warehouse views.

Feature completeness passed live acceptance after scoping the reference feature relation to
observed rows:

| Signal | Result |
|---|---|
| Feature model | `int_sales_store_daily` |
| Feature date | `2017-08-15` |
| Required columns | `4` |
| Completeness status | `healthy` |
| Alerting | `false` |

The focused dbt build completed with `PASS=9 WARN=0 ERROR=0`, including its unit test and five
data tests. The then-current four-view live evaluator subsequently returned zero active alerts.

## Alert and infrastructure validation

- The versioned YAML alert/SLO contract passed validation and deterministic hashing tests.
- Synthetic stale, low-coverage, and unhealthy-pipeline signals produced the expected severities.
- Structured-log routing and environment-indirected webhook routing passed unit tests.
- The executable runner queried all four then-configured live warehouse views directly and
  returned zero active alerts. Controlled stale-publication, low-coverage, and failed-pipeline
  fixtures emitted exactly three structured alerts with the configured `page`, `ticket`, and
  `page` severities.
- Terraform formatting and validation passed for both development and production environments
  with alert resources disabled by default.
- The opt-in infrastructure defines a log-based failure metric and a Cloud Monitoring alert policy;
  notification channel IDs remain environment inputs rather than repository secrets.
- Terraform validation passed for the opt-in Cloud Run Job, authenticated Cloud Scheduler trigger,
  structured SLO log metric, and notification policy in both dev and prod.

## Regression validation

The full Python suite passed:

```text
367 passed, 7 warnings
Total coverage: 76% (required: 75%)
```

dbt parsing, monitoring compilation, schema tests, data tests, and the new coverage/freshness unit
tests passed. Targeted formatting, import sorting, linting, and type checking also passed.

## Defect corrected during acceptance

The first freshness query treated every forecast contract as publication-monitored. That produced
a false missing-publication alert for an older draft-only contract. Publication paging is now
explicitly opt-in through `publication_monitored_contracts`; prediction coverage continues to
evaluate every run with declared expected output. The final freshness result contains only the
hierarchical delivery contract and reports it as fresh.

The first feature-completeness query evaluated future date-spine rows whose targets are
intentionally null, producing a false page. Monitored feature relations now support an explicit
`scope_column`/`scope_value`; the reference contract evaluates `data_split_source = 'train'` and
returns healthy while a unit fixture still proves null degradation and entity loss alert.

## Remaining production activation

This acceptance proves the repository implementation, direct warehouse evaluation, and structured
log delivery. The hosted schedule and channel-routing resources are now implemented and validated
but remain opt-in. Production paging still requires an enabled Terraform plan/apply with a real
image digest and notification channel IDs, followed by a witnessed external notification.
Realized calibration was subsequently accepted the same day; see
[Realized forecast calibration acceptance](forecast_realized_calibration_2026-08-11.md).
Target/feature drift and cost monitoring remain separate increments in the broader monitoring spec.
