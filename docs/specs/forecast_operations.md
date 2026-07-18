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

### 6. End-to-end scheduled publication path

This section is the authoritative integration contract for scheduled forecast publication. The
component specs define their own algorithms and schemas; the publication flow owns their ordering,
failure semantics, and the decision to expose a forecast to downstream consumers.

```text
load contract and champion
  -> select eligible series
  -> classify and route strategy
  -> generate base forecasts
  -> calibrate quantiles
  -> reconcile configured hierarchy
  -> validate output and quality gates
  -> create draft publication
  -> approve or queue exceptions
  -> publish version
  -> confirm delivery and monitor
```

The stages exchange canonical forecast rows keyed by `forecast_run_id`,
`forecast_contract_hash`, `forecast_origin`, `entity_key_json`, `target_date`, and `horizon`.
Every row entering publication must also carry:

```text
model_run_id
model_id
forecast_strategy
fallback_reason
confidence_flag
calibration_method
calibration_run_id
prediction_p10
prediction_p50
prediction_p90
hierarchy_version
reconciliation_method
reconciliation_run_id
feature_version
data_cutoff
code_sha
```

Calibration runs before reconciliation. Reconciliation applies to every configured quantile, not
only P50. The reconciler must preserve nonnegative values and quantile ordering
`P10 <= P50 <= P90`; if the selected reconciliation method cannot satisfy both coherence and
quantile ordering within tolerance, the run fails its publication gate rather than silently
publishing a partially coherent result.

#### Failure and exception behavior

- Contract, eligibility, routing, calibration, reconciliation, and output validation failures stop
  publication for the affected scope and write an auditable exception.
- A fallback strategy is allowed only when declared by the forecast contract. Its reason and
  confidence flag must be persisted.
- Partial publication is disabled by default. A contract may opt into it only with an explicit
  minimum-completeness threshold and an exception record for every excluded scope.
- Retries reuse the same logical `forecast_run_id`; a changed input, contract, model, or code SHA
  creates a new run and publication version.
- Published rows are append-only. Correction creates a revision that supersedes the previous
  version; it never overwrites it.

#### Publication gates

Before approval or automatic publication, the flow must verify:

- canonical-key uniqueness and required provenance fields
- complete configured horizons and quantiles for eligible series
- quantile ordering and calibration coverage thresholds
- hierarchical coherence within the contract tolerance
- freshness and point-in-time cutoff compliance
- configured completeness, confidence, and exception-count thresholds

The Prefect deployment must expose contract name/version, forecast origin, publication mode
(`draft_only`, `require_approval`, or `auto_publish`), and an idempotency key. Task retries may not
repeat already committed stage writes. The publication record stores the Prefect flow-run ID and
the component run IDs so an operator can trace a published value back through routing,
calibration, reconciliation, model, features, and source cutoff.

## Implementation plan

1. Add `docs/forecast_operations.md`.
2. Add workflow DDL and dbt staging models.
3. Add status transition validation utilities.
4. Split Prefect daily scoring from retrain/tune flows.
5. Add CLI commands for approve/publish/supersede operations.
6. Add FVA dbt mart.
7. Add runbooks for retries, partial failures, backfills, revisions, and champion rollback.
8. Add the scheduled publication flow using the stage ordering and gates defined above.

## Testing & validation

- Unit tests for status transitions.
- Idempotency tests for publish and supersede operations.
- dbt tests for override audit fields and reason codes.
- Prefect flow test confirming daily scoring does not retrain.
- Fixture test for FVA calculation.
- Integration fixture proving published rows are routed, calibrated, reconciled, contract-valid,
  and traceable to their component run IDs.
- Failure-path tests proving invalid quantile ordering, incoherent hierarchies, and incomplete
  horizons cannot create a published version.

## Acceptance criteria

- A forecast can be scored, overridden, approved, published, and superseded without losing the original statistical forecast.
- Publication is idempotent by run/version ID.
- Daily scoring can run independently from retraining and tuning.
- FVA is queryable once actuals arrive.
- A scheduled run executes routing, forecasting, calibration, reconciliation, validation, and
  publication in the documented order.
- Every published row is calibrated, coherent where a hierarchy is configured, versioned,
  idempotent, and traceable to its source runs.

## Related documents

- [Forecast contract and canonical output](forecast_contract_and_output.md)
- [Backtesting and model lifecycle](backtesting_and_model_lifecycle.md)
- [Monitoring and SLOs](monitoring_and_slos.md)
- [Integration contracts](integration_contracts.md)

{% enddocs %}
