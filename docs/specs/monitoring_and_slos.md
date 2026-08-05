{% docs spec_monitoring_and_slos %}

# SPEC: Monitoring, alerts, and SLOs

**Status:** Proposed
**Roadmap reference:** [Specs overview](README.md) — P1 "Expand monitoring and SLOs"

---

## Summary

The repo has accuracy monitoring and operational notes, but a platform needs end-to-end SLOs and alerting across source freshness, pipeline execution, forecast coverage, publication freshness, data drift, accuracy, calibration, and cost.

This spec adds `docs/monitoring_and_slos.md`, metric marts, alert policies, and configurable notification routing.

## Goals

- Define SLOs for forecast freshness, completeness, pipeline availability, and maximum publish delay.
- Monitor source freshness, schema changes, feature completeness, prediction coverage, stale publication, error, bias, calibration, drift, and cost.
- Route alerts to configurable destinations.
- Manage GCP alert resources through Terraform where possible.
- Extend existing prediction accuracy monitoring rather than duplicate it.

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
| `forecast_source_freshness` | source lateness and missing feeds |
| `forecast_feature_completeness` | nulls, schema changes, entity coverage |
| `forecast_prediction_coverage` | eligible vs predicted entities/horizons |
| `forecast_publication_freshness` | stale or missing published forecasts |
| `forecast_accuracy_by_horizon` | error, bias, WAPE by horizon/segment |
| `forecast_calibration` | coverage, interval width, pinball loss |
| `forecast_drift` | target and feature drift |
| `forecast_pipeline_health` | success, duration, retries, cost labels |

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

1. Add `docs/monitoring_and_slos.md`.
2. Add monitoring mart models and schema tests.
3. Add alert policy YAML and loader.
4. Add Terraform alert module or extend existing modules.
5. Add Prefect/GCP notification wiring for local and hosted paths.
6. Update ops runbooks to point from alert to remediation.

## Testing & validation

- dbt unit tests for coverage/freshness calculations.
- Terraform validate with alert resources disabled and enabled via fixture variables.
- Synthetic failure rows that trigger alert queries.
- End-to-end smoke test showing stale publication detection.

## Acceptance criteria

- SLOs are documented with thresholds and owners.
- Missing or stale published forecasts are detectable.
- Coverage and accuracy are monitored by horizon/segment.
- At least one alert path is configurable without code changes.

## Related documents

- [Prediction accuracy monitoring](prediction_accuracy_monitoring.md)
- [Forecast operations](forecast_operations.md)
- [Terraform modules](terraform_modules.md)
- [IaC and GCP operations](../iac.md)
- [Scheduled forecast publication pipeline](scheduled_forecast_publication_pipeline.md)

{% enddocs %}
