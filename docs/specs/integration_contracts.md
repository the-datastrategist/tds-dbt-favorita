{% docs spec_integration_contracts %}

# SPEC: Integration contracts and forecast delivery

**Status:** In progress
**Roadmap reference:** [Specs overview](README.md) — P2 "Publish through a standard integration contract"

---

## Summary

The consumption layer now exposes stable current/by-run warehouse views, operations audit views,
an explicit-run GCS batch export, version-level publication events, append-only delivery
confirmation, and an IAM-authenticated operations API. Read-only retrieval is live accepted;
append-only lifecycle mutations are implemented locally and disabled by default. An outbound
webhook adapter remains next.

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

Implemented read-only endpoints:

```text
GET /v1/forecasts/current
GET /v1/forecasts/runs/{run_id}?publication_version=...
```

Implemented mutation endpoints:

```text
POST /v1/overrides
POST /v1/forecast-runs/{run_id}/approve
POST /v1/forecast-runs/{run_id}/publish
```

API behavior:

- current retrieval resolves one delivered run/version/destination before returning rows;
- explicit retrieval requires run ID, publication version, and destination;
- every retrieval verifies complete publication cardinality and uses deterministic pagination;
- publish endpoint is idempotent for the same `run_id`.
- approval/publish endpoints reject invalid status transitions.
- responses include contract name/hash and publication version.

### 4. Batch export command

Provide a generic export command:

```bash
make forecast-export FORECAST_RUN_ID=... VERSION=... DESTINATION=gs://...
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
4. **Complete:** read-only retrieval, append-only lifecycle mutation endpoints, and opt-in Cloud
   Run write permissions are implemented.
5. **Complete:** add idempotency keys, publication-event table, and delivery-event table.
6. **Complete:** stable warehouse, batch export, and read-only API examples are documented.

## Testing & validation

- dbt tests for one current published forecast per comparable key/entity/horizon.
- API unit tests for current/explicit version resolution, filters, pagination, structured errors,
  and incomplete-publication rejection.
- Export smoke test for CSV and Parquet.
- Contract fixture tests for response payload shape.

## Current implementation

The stable warehouse boundary now includes current, explicit-run, publication-audit,
override-audit, publication-event, and delivery-state dbt views. A live-accepted export command writes one explicit published run version to GCS as
CSV or Parquet without overwriting an existing delivery. See the
[live acceptance evidence](../acceptance/forecast_operations_delivery_2026-08-11.md). The
[integration contract guide](../integration_contracts.md) defines view usage, version pins,
export behavior, and compatibility policy. Version-level publication events and independent,
append-only delivery confirmation are live accepted. The private, live-accepted read-only retrieval
API resolves one complete delivered or explicitly pinned version with deterministic pagination and
structured errors. Override, approval, and publication endpoints use explicit idempotency keys and
complete approval sets; production mutation activation and the outbound webhook adapter remain
open. See the [retrieval API acceptance evidence](../acceptance/forecast_retrieval_api_2026-08-11.md).

## Acceptance criteria

- A downstream consumer can retrieve an explicit published forecast version from a stable view.
- A read-only API never returns incomplete or mixed publication versions.
- Publication can be retried safely with the same run ID.
- Exported files include contract, run, entity, origin, target date, horizon, and published forecast value.

## Related documents

- [Forecast contract and canonical output](forecast_contract_and_output.md)
- [Forecast operations](forecast_operations.md)
- [Hierarchical reconciliation](hierarchical_reconciliation.md)

{% enddocs %}
