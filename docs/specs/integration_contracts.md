{% docs spec_integration_contracts %}

# SPEC: Integration contracts and forecast delivery

**Status:** In progress
**Roadmap reference:** [Specs overview](README.md) — P2 "Publish through a standard integration contract"

---

## Summary

The current consumption layer is mostly BI/dashboard staging. A platform needs stable contracts for downstream systems: warehouse views, batch exports, retrieval APIs, override/approval/publication APIs, and publication events.

This spec adds `docs/integration_contracts.md`, versioned table/view contracts, export commands, API concepts, and idempotent publication semantics.

## Goals

- Define stable warehouse consumption views for published forecasts.
- Add batch export commands for common downstream paths.
- Define forecast retrieval, override, approval, and publication API contracts.
- Emit a publication event/webhook after successful publication.
- Require explicit forecast version/run IDs for all publish and retrieval operations.
- Keep publish operations idempotent.

## Non-goals

- Building every enterprise integration in the first cut.
- Implementing authentication/authorization for a public API beyond local/service-account patterns.
- Replacing dbt Docs lineage; this adds operational contracts.

## Design

### 1. Documentation

Add `docs/integration_contracts.md` with:

- canonical table/view schema
- API endpoint reference
- batch export formats
- webhook/event payload
- versioning and deprecation policy
- idempotency behavior

### 2. Warehouse contract

Add stable views:

| View | Purpose |
|------|---------|
| `published_forecasts_current` | Latest published forecast per contract/entity/horizon |
| `published_forecasts_by_run` | Explicit run/version retrieval |
| `forecast_publication_audit` | Status and delivery metadata |
| `forecast_overrides_audit` | Override history for consumers |

Views should be backward-compatible once documented.

### 3. API concepts

Minimum endpoints:

```text
GET  /v1/forecasts
POST /v1/overrides
POST /v1/forecast-runs/{run_id}/approve
POST /v1/forecast-runs/{run_id}/publish
```

API behavior:

- `GET /v1/forecasts` requires either `run_id` or `published=current`.
- publish endpoint is idempotent for the same `run_id`.
- approval/publish endpoints reject invalid status transitions.
- responses include contract name/hash and publication version.

### 4. Batch export command

Provide a generic export command:

```bash
make forecast-export FORECAST_RUN_ID=... DESTINATION=gs://...
```

Initial formats:

- CSV
- Parquet
- BigQuery table copy

### 5. Publication events

Emit event rows and optional webhook payload:

```json
{
  "event_type": "forecast.published",
  "forecast_run_id": "...",
  "forecast_contract_name": "...",
  "publication_version": "...",
  "published_at": "...",
  "row_count": 12345
}
```

## Implementation plan

1. Add `docs/integration_contracts.md`.
2. Add stable dbt views for published forecasts.
3. Add export command and destination configuration.
4. Add minimal FastAPI or Cloud Run-ready API skeleton.
5. Add idempotency keys and publication event table.
6. Add examples for BI and replenishment-style consumers.

## Testing & validation

- dbt tests for one current published forecast per comparable key/entity/horizon.
- API unit tests for idempotent publish and invalid transitions.
- Export smoke test for CSV and Parquet.
- Contract fixture tests for response payload shape.

## Current implementation

The stable warehouse boundary now includes current, explicit-run, publication-audit, and
override-audit dbt views. A validated export command writes one explicit published run to GCS as
CSV or Parquet without overwriting an existing delivery. The
[integration contract guide](../integration_contracts.md) defines view usage, version pins,
export behavior, and compatibility policy. A retrieval/service API, publication events/webhooks,
and independent delivery-status confirmation remain open.

## Acceptance criteria

- A downstream consumer can retrieve an explicit published forecast version from a stable view.
- Publication can be retried safely with the same run ID.
- Exported files include contract, run, entity, origin, target date, horizon, and published forecast value.

## Related documents

- [Forecast contract and canonical output](forecast_contract_and_output.md)
- [Forecast operations](forecast_operations.md)
- [Hierarchical reconciliation](hierarchical_reconciliation.md)

{% enddocs %}
