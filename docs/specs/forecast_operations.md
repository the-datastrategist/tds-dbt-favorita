{% docs spec_forecast_operations %}

# SPEC: Forecast operations, overrides, approval, and publication

**Status:** In progress
**Roadmap reference:** [Specs overview](README.md) — P1 "Separate daily scoring from retraining and tuning" and P2 "Build a forecast operations layer"

---

## Summary

The platform now operates forecasts as append-only business artifacts through explicit override,
approval, publication, revision, and rollback commands. The API now exposes separate, append-only
override, approval, and publication mutations; remaining work is the planner-facing UI. Forecast Value Added and downstream
delivery confirmation are implemented through tested warehouse and append-only integration
contracts.

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

- every backtest candidate vs the configured simple benchmark on an identical evaluation population
- statistical forecast vs actual
- planner-adjusted forecast vs actual
- approved/published forecast vs actual

Metrics are computed by planner/team, reason code, horizon, segment, grain, and hierarchy level where
available. A comparison is not valid unless evaluation populations match and actual coverage is
complete; invalid comparisons expose a reason and null FVA.

### 6. End-to-end scheduled publication path

The authoritative integration contract is the
[scheduled forecast publication pipeline](scheduled_forecast_publication_pipeline.md). That spec
owns stage ordering, pinned run identity, locks, retries, cross-stage row envelopes, numerical
validation, partial-failure policy, and atomic visibility. This spec owns the business lifecycle
after a complete draft exists: override, approval, publication, revision, rollback, and delivery
status.

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
`forecast_contract_hash`, `forecast_origin`, `series_key`, `target_timestamp`, and `horizon`.
They also preserve `entity_key_json` as the structured representation of the series identity.
Daily implementations may expose `target_date` as a compatibility projection.
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

The Prefect parameter and retry contracts, including `draft_only`, `require_approval`, and
`auto_publish`, are defined in the pipeline spec. The publication record stores the Prefect
flow-run ID and component run IDs so an operator can trace a published value back through routing,
calibration, reconciliation, model, features, and source cutoff.

## Implementation plan

1. Add `docs/forecast_operations.md`.
2. Add workflow DDL and dbt staging models.
3. Add status transition validation utilities.
4. Split Prefect daily scoring from retrain/tune flows.
5. Add CLI commands for approve/publish/supersede operations.
6. **Complete:** add backtest and operations FVA dbt marts.
7. Add runbooks for retries, partial failures, backfills, revisions, and champion rollback.
8. Add the scheduled publication flow using the stage ordering and gates defined above.

## Current implementation

The scheduled flow now resolves and pins the governed champion, scores independently from
retraining, persists stage and validation evidence, and exposes a draft only after routing,
calibration, reconciliation, and blocking gates pass. A separate manual flow validates a concrete
run and can create retry-safe approval and publication records in `auto_publish` mode.

Explicit planner override, approve/publish, revision, and rollback commands now write deterministic,
append-only records. Approval selects audited overrides without changing the statistical
forecast; rollback republishes a complete prior version under a new version with revision
lineage. The [operations runbook](../forecast_operations.md) documents retry, revision, backfill,
and delivery recovery. Append-only delivery confirmation, retry, abandonment, and monitoring are
live accepted. Backtest and operations FVA marts now implement configured-benchmark comparison,
planner/published accuracy attribution, and fail-closed coverage semantics. A planner UI remains
open; read-only retrieval is live accepted and lifecycle mutation endpoints are locally validated. See the
[FVA acceptance evidence](../acceptance/forecast_value_added_2026-08-11.md) and
[retrieval API acceptance evidence](../acceptance/forecast_retrieval_api_2026-08-11.md). Local API
mutation evidence is recorded in
[forecast lifecycle mutation acceptance](../acceptance/forecast_lifecycle_mutation_api_2026-08-18.md).

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
- Backtest FVA is queryable from persisted rolling-origin metrics; operations FVA becomes
  comparable once complete target-date actuals arrive.
- A scheduled run executes routing, forecasting, calibration, reconciliation, validation, and
  publication in the documented order.
- Every published row is calibrated, coherent where a hierarchy is configured, versioned,
  idempotent, and traceable to its source runs.

## Related documents

- [Forecast contract and canonical output](forecast_contract_and_output.md)
- [Backtesting and model lifecycle](backtesting_and_model_lifecycle.md)
- [Monitoring and SLOs](monitoring_and_slos.md)
- [Integration contracts](integration_contracts.md)
- [Scheduled forecast publication pipeline](scheduled_forecast_publication_pipeline.md)

{% enddocs %}
