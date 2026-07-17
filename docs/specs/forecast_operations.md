{% docs spec_forecast_operations %}

# SPEC: Forecast operations, overrides, approval, and publication

**Status:** Proposed
**Roadmap reference:** [`demand_forecasting_platform_recommendations.md`](../demand_forecasting_platform_recommendations.md) — P1 "Separate daily scoring from retraining and tuning" and P2 "Build a forecast operations layer"

---

## Summary

The current platform can run dbt, train models, predict, track experiments, and monitor accuracy. It does not yet operate forecasts as business artifacts with review, override, approval, publication, revision, rollback, and downstream confirmation.

This spec adds `docs/forecast_operations.md`, operating cadences, lifecycle tables, workflow APIs, and runbooks for retries, partial failures, backfills, revisions, and champion rollback.

## Goals

- Separate daily scoring from retraining, tuning, and champion promotion.
- Add forecast statuses and workflow transitions.
- Support planner overrides with reason codes, comments, and audit trail.
- Add approval, freeze, publish, supersede, and rollback flows.
- Measure Forecast Value Added (FVA).
- Provide runbooks for operational failures and forecast revisions.

## Non-goals

- Building a polished planner UI in the first implementation. Tables and APIs should support it.
- Defining downstream API details beyond handoff to [integration contracts](integration_contracts.md).
- Reconciliation algorithms; publication consumes reconciled outputs when configured.

## Design

### 1. Documentation

Add `docs/forecast_operations.md` covering:

- daily/weekly/monthly cadence
- run state machine
- forecast status lifecycle
- exception queue
- override and approval rules
- backfill/revision/rollback procedures
- FVA measurement

### 2. Operating cadence

Default cadence:

| Cadence | Workload |
|---------|----------|
| daily | ingest, validate, score active champion, publish, monitor |
| weekly or trigger-based | retrain challengers |
| monthly or trigger-based | hyperparameter optimization |
| gated | promote champion |

Update Prefect deployments so daily scoring can run without retraining.

### 3. Workflow tables

Minimum tables:

| Table | Purpose |
|-------|---------|
| `forecast_exceptions` | High-impact or low-confidence rows requiring planner review |
| `forecast_overrides` | Planner entered changes with reason/comment |
| `forecast_approvals` | Approval decisions and actor metadata |
| `forecast_publications` | Published versions and delivery status |
| `forecast_revisions` | Supersession and rollback lineage |

### 4. Status transitions

Allowed status flow:

```text
draft -> approved -> published -> superseded
draft -> failed
approved -> superseded
published -> superseded
```

Override rows must never overwrite statistical forecasts. They produce an adjusted value used in approved/published forecasts.

### 5. Forecast Value Added

FVA mart compares:

- statistical forecast vs actual
- planner-adjusted forecast vs actual
- approved/published forecast vs actual

Metrics should be computed by planner/team, reason code, horizon, segment, and hierarchy level where available.

## Implementation plan

1. Add `docs/forecast_operations.md`.
2. Add workflow DDL and dbt staging models.
3. Add status transition validation utilities.
4. Split Prefect daily scoring from retrain/tune flows.
5. Add CLI commands for approve/publish/supersede operations.
6. Add FVA dbt mart.
7. Add runbooks for retries, partial failures, backfills, revisions, and champion rollback.

## Testing & validation

- Unit tests for status transitions.
- Idempotency tests for publish and supersede operations.
- dbt tests for override audit fields and reason codes.
- Prefect flow test confirming daily scoring does not retrain.
- Fixture test for FVA calculation.

## Acceptance criteria

- A forecast can be scored, overridden, approved, published, and superseded without losing the original statistical forecast.
- Publication is idempotent by run/version ID.
- Daily scoring can run independently from retraining and tuning.
- FVA is queryable once actuals arrive.

## Related documents

- [Forecast contract and canonical output](forecast_contract_and_output.md)
- [Backtesting and model lifecycle](backtesting_and_model_lifecycle.md)
- [Monitoring and SLOs](monitoring_and_slos.md)
- [Integration contracts](integration_contracts.md)

{% enddocs %}
