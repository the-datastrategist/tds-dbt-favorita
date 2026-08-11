{% docs spec_monitoring_and_slos %}

# SPEC: Monitoring, alerts, and SLOs

**Status:** In progress
**Roadmap reference:** [Specs overview](README.md) — P1 "Expand monitoring and SLOs"

---

## Summary

The repo now has accuracy monitoring, mode-aware source ingestion health, scheduled pipeline
health, publication freshness, prediction coverage, feature completeness, realized calibration,
and an opt-in hosted alert evaluator. A complete platform still needs production alert-channel
activation plus end-to-end target/feature drift and cost signals.

The source and scheduled-pipeline health slice passed live GCP acceptance on 2026-08-06. The
publication-freshness, prediction-coverage, feature-completeness, and realized-calibration slices
passed live BigQuery acceptance on 2026-08-11. Together, the evidence covers static-demo freshness
semantics, policy lineage, stage order,
blocking gates, output cardinality, horizon coverage, publication age, quantiles, and forecast
provenance.

This spec adds `docs/monitoring_and_slos.md`, metric marts, alert policies, and configurable notification routing.

## Goals

- Define SLOs for forecast freshness, completeness, pipeline availability, and maximum publish delay.
- Monitor source freshness, schema changes, feature completeness, prediction coverage, stale publication, error, bias, calibration, drift, and cost.
- Route alerts to configurable destinations.
- Manage GCP alert resources through Terraform where possible.
- Extend existing prediction accuracy monitoring rather than duplicate it.
- Distinguish immutable demonstration snapshots from continuously updating sources without
  weakening loader, watermark, lineage, or pipeline-health controls.

## Non-goals

- Incident management tooling beyond alert emission.
- Guaranteeing every client has the same alert channels. Destinations must be configurable.
- Full root-cause automation.

## Design

### 1. Documentation

Add `docs/monitoring_and_slos.md` with:

- metric catalog
- SLO definitions
- alert severity levels
- runbook links
- tuning guidance
- example dashboards

### 2. Monitoring marts

Add or extend dbt marts:

| Mart | Signal |
|------|--------|
| `forecast_source_health` | source execution and mode-aware lateness |
| `forecast_feature_completeness` | nulls, schema changes, entity coverage |
| `forecast_prediction_coverage` | eligible vs predicted entities/horizons |
| `forecast_publication_freshness` | stale or missing published forecasts |
| `forecast_accuracy_by_horizon` | error, bias, WAPE by horizon/segment |
| `forecast_realized_calibration` | realized P10-P90 coverage, interval width, and median bias by contract/horizon |
| `forecast_drift` | target and feature drift |
| `forecast_pipeline_health` | success, duration, retries, cost labels |

Implemented source policies declare `static_demo` or `continuous`. Static snapshots do not fail
wall-clock freshness merely because their event dates are historical. Continuous sources fail once
the latest successful ingestion exceeds the configured cadence plus grace period. Both modes
persist immutable ingestion evidence and alert on unsuccessful loads.

The scheduled publication pipeline additionally emits per-stage status, duration, attempt count,
input/output row counts, exception counts, lock ownership, and component run IDs. Monitoring must
distinguish a technically successful stage from a run that failed its publication gates, and must
alert when a nonterminal run exceeds the contract's maximum duration.

### 3. Alert policy config

Add a YAML alert contract:

```yaml
alerts:
  notification_channel: slack_forecasting_ops
  policies:
    - name: stale_forecast_publication
      severity: page
      threshold_minutes: 120
    - name: prediction_coverage_low
      severity: ticket
      min_coverage_pct: 0.98
```

### 4. Terraform-managed alerts

Extend Terraform with optional alerting resources for:

- Cloud Logging filters for failed Vertex/Pipeline jobs.
- Cloud Monitoring alert policies for scheduler failures and publish delay.
- Notification channel IDs supplied by environment variables or `.tfvars`.

Keep alert resources disabled by default until destination IDs are configured.

### 5. Integration with existing tests

The existing `assert_no_material_accuracy_drift` remains useful, but should become one signal in the wider monitoring catalog. Warn/error thresholds should be configurable by contract or environment.

## Implementation plan

1. **Complete:** add `docs/monitoring_and_slos.md` and source-mode policy.
2. **Complete:** add source and scheduled-pipeline health marts with schema tests.
3. **Complete:** add versioned SLO/alert policy YAML, validation, and deterministic policy hash.
4. **Partial:** prediction coverage, publication freshness, feature completeness, and realized
   calibration are implemented; target/feature drift and cost remain.
5. **Complete:** add an opt-in Terraform log metric and Cloud Monitoring failure policy.
6. **Partial:** direct warehouse evaluation, structured-log routing, environment-indirected
   webhook routing, and an opt-in Cloud Scheduler → Cloud Run Job are implemented; applying the
   hosted path with real notification channels remains.
7. **Complete:** update operator runbooks from each implemented alert to remediation.

## Testing & validation

- dbt unit tests for coverage, freshness, feature-completeness, and realized-calibration
  calculations.
- Terraform validate with alert resources disabled and enabled via fixture variables.
- Synthetic failure rows that trigger alert queries.
- End-to-end smoke test showing stale publication detection.

## Acceptance criteria

- SLOs are documented with thresholds and owners.
- Missing or stale published forecasts are detectable.
- Coverage and accuracy are monitored by horizon/segment.
- At least one alert path is configurable without code changes.

## Current implementation status

The implementation now satisfies the documented SLO, stale/missing publication, prediction
coverage, feature-completeness, and configurable alert-path criteria. Python validation, dbt
tests, and disabled
Terraform validation pass, and the freshness, coverage, direct-query, and structured-log paths
passed live BigQuery acceptance on 2026-08-11. An enabled Terraform plan/apply with real channel
IDs and a witnessed external notification remain required before this spec can be marked shipped.
Broader drift and cost signals also remain in scope.

## Related documents

- [Prediction accuracy monitoring](prediction_accuracy_monitoring.md)
- [Forecast operations](forecast_operations.md)
- [Terraform modules](terraform_modules.md)
- [IaC and GCP operations](../iac.md)
- [Scheduled forecast publication pipeline](scheduled_forecast_publication_pipeline.md)
- [Live forecast monitoring acceptance](../acceptance/forecast_monitoring_2026-08-06.md)
- [Live monitoring and SLO acceptance](../acceptance/monitoring_slos_2026-08-11.md)
- [Realized calibration acceptance](../acceptance/forecast_realized_calibration_2026-08-11.md)

{% enddocs %}
