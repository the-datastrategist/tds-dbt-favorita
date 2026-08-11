{% docs spec_scheduled_forecast_publication_pipeline %}

# SPEC: Scheduled forecast publication pipeline

**Status:** Shipped
**Roadmap reference:** [Specs overview](README.md) — operationalize calibrated, reconciled, governed forecasts

---

## Problem statement

The platform can score champion models, route sparse series, calibrate uncertainty, reconcile
hierarchies, and persist forecast-operation records, but these capabilities are not yet one
governed production transaction. Operators and downstream consumers need a scheduled path that
turns a pinned model and point-in-time input snapshot into exactly one validated, traceable draft
or published forecast version without exposing partial stage output.

## Goals

- Produce a complete draft forecast for every scheduled contract and origin through one
  deterministic, retry-safe run.
- Guarantee that every visible draft or publication is contract-valid, point-in-time correct,
  quantile ordered, and hierarchically coherent when reconciliation is configured.
- Preserve immutable lineage from the published value through routing, calibration,
  reconciliation, champion selection, features, data cutoffs, code, and orchestration.
- Prevent failed, incomplete, stale, or concurrently superseded runs from becoming publishable.
- Emit stage health, quality metrics, and actionable exceptions for operators.

## Non-goals

- Planner UI, override editing, and human workflow presentation remain in
  [forecast operations](forecast_operations.md).
- Model training, challenger evaluation, and champion promotion remain in
  [backtesting and model lifecycle](backtesting_and_model_lifecycle.md).
- Delivery-specific APIs, files, and webhooks remain in
  [integration contracts](integration_contracts.md).
- Inventory optimization and order recommendations are downstream consumers, not pipeline stages.

## User stories

### Forecast operator

- As a forecast operator, I want one scheduled run with a clear terminal state so that I can tell
  whether a complete forecast is ready without inspecting every component job.
- As a forecast operator, I want failures linked to stage, scope, and reason so that I can retry or
  remediate without publishing unaffected-looking but incomplete data accidentally.
- As a forecast operator, I want retries to reuse committed stage results so that recovery does not
  duplicate forecasts or publication versions.

### Planner and approver

- As a planner, I want only complete validated drafts to enter review so that overrides are made
  against coherent forecasts.
- As an approver, I want every value traceable to its model and transformations so that approval is
  auditable.

### Downstream consumer

- As a downstream consumer, I want atomic forecast versions so that one query never mixes an old
  hierarchy or horizon with a new one.

## Authoritative stage order

This spec owns orchestration order, cross-stage contracts, failure behavior, and visibility. The
component specs own their algorithms.

```text
validate contract and acquire scope lock
  -> pin champion, code, feature snapshot, and source cutoffs
  -> freeze eligible entity/horizon set
  -> classify series and select declared strategies
  -> generate immutable base forecasts
  -> calibrate configured quantiles
  -> reconcile every configured quantile
  -> jointly validate coherence and quantile ordering
  -> persist complete canonical draft
  -> approve automatically, await approval, or stop at draft
  -> publish one immutable version
  -> confirm downstream delivery and emit monitoring signals
```

Routing occurs before calibration because the residual distribution must correspond to the
selected strategy. Reconciliation occurs after calibration because every published quantile must
be coherent. No component may publish directly or change the pinned champion during a run.

## P0 requirements

### P0.1 Run identity and pinned inputs

One logical `forecast_run_id` is the stable hash of:

```text
forecast_contract_hash
forecast_origin
champion_candidate_id
model_run_id
feature_version
data_cutoff_set
eligibility_snapshot_id
code_sha
```

The Prefect attempt ID is operational metadata and is not part of this logical identity. A retry
with identical inputs reuses `forecast_run_id`; any material input change creates a new run.

Acceptance criteria:

- Given identical pinned inputs, two attempts produce the same run and row IDs.
- Given a changed champion, contract, cutoff, feature version, eligibility snapshot, or code SHA,
  a new run ID is produced.
- The champion candidate and artifact are resolved once before scoring and never re-resolved
  inside the run.

### P0.2 Canonical stage envelope

Every stage receives and returns rows with the canonical business key:

```text
forecast_run_id
forecast_contract_hash
forecast_origin
entity_key_json
target_date
horizon
```

Quantiles may remain wide (`prediction_p10`, `prediction_p50`, `prediction_p90`) in the canonical
output. A normalized internal stage representation adds `quantile` to that business key; a stage
must not mix wide and normalized representations in the same output contract.

Every stage result also records its component run ID, input fingerprint, status, row count,
started/completed timestamps, and error summary. Base, calibrated, and reconciled values remain
separately queryable; later stages never overwrite earlier values.

Acceptance criteria:

- Every stage rejects duplicate canonical keys.
- Stage retries are insert-only no-ops for already committed matching IDs.
- A conflicting payload for an existing ID fails rather than updating historical evidence.

### P0.3 Eligibility, routing, and fallback

Eligibility is frozen before scoring. Strategy selection applies once per
entity/origin/target-date/horizon and all quantiles inherit that strategy. Only contract-declared
fallbacks are allowed. Missing eligibility inputs or exhausted fallbacks create exceptions.

Acceptance criteria:

- Every eligible key has one strategy or one blocking exception.
- Cold-start and intermittent-demand paths persist `forecast_strategy`, `fallback_reason`, and
  `confidence_flag`.
- Undeclared fallbacks cannot create a draft row.

### P0.4 Calibration and reconciliation

Calibration emits every configured quantile using out-of-sample residual evidence for the
selected strategy and horizon. Reconciliation operates on each quantile. A joint numerical
projection must satisfy both hierarchy coherence and monotonic quantiles; repeatedly sorting
quantiles independently is prohibited because it can break coherence.

If the joint constraints do not converge within configured tolerances and iteration limits, the
affected scope fails. A contract with no hierarchy records `reconciliation_method = 'none'` and a
null reconciliation run ID explicitly allowed by contract validation.

Acceptance criteria:

- `P10 <= P50 <= P90` for every canonical key when those quantiles are configured.
- Child totals equal parent totals within the configured absolute and relative tolerances for
  every quantile.
- Calibration and reconciliation run IDs are present when their stages apply.
- Unreconciled values are never substituted silently after reconciliation failure.

### P0.5 Publication gates

Before a draft becomes visible, validation checks:

- canonical-key uniqueness and required lineage;
- configured horizon and quantile completeness against the frozen eligibility snapshot;
- nonnegative values when required by the target contract;
- quantile ordering and calibration coverage thresholds;
- hierarchy membership and coherence tolerances;
- source freshness and point-in-time cutoff compliance;
- confidence, completeness, and blocking-exception thresholds;
- champion and contract pins still match the run declaration.

Gate results are immutable records linked to `forecast_run_id`. Warnings may create exceptions;
blocking failures set the run to `failed` and cannot create an eligible draft.

### P0.6 State, atomic visibility, and partial failure

Pipeline-run states are:

```text
planned -> running -> validating -> draft
planned | running | validating -> failed
draft -> approved -> published -> superseded
draft | approved -> superseded
```

`planned`, `running`, and `validating` are run states, not forecast artifact states. Artifact
statuses begin at `draft` and follow the lifecycle defined by Forecast Operations.

Stage tables may contain committed evidence while a run is executing, but consumer-facing models
expose rows only when the run reaches `draft`, `approved`, or `published`. The draft transition is
the atomic visibility boundary.

Partial publication is disabled by default. An opted-in contract must define a minimum
completeness threshold, allowed exclusion categories, and maximum blocking-exception count. Every
excluded scope receives an exception record; hierarchy ancestors affected by exclusion must be
reconciled and validated again before visibility.

### P0.7 Concurrency and scheduling

Only one active run may hold the lock for a contract and forecast origin. A newer origin may run
concurrently only when it writes an independent publication version and resource limits permit.
Lock expiry requires heartbeat loss plus a configured grace period; takeover writes an audit
event. Backfills never supersede a newer publication unless invoked in explicit revision mode.

The scheduled Prefect deployment exposes:

```text
forecast_contract_name
forecast_origin
publication_mode: draft_only | require_approval | auto_publish
idempotency_key
revision_of_publication_id (optional)
```

### P0.8 Exceptions, observability, and delivery handoff

Every failure records stage, canonical scope, severity, reason code, retryability, and evidence
URI or JSON. A successful run emits duration, retry count, eligible/predicted/published counts,
coverage, fallback rate, low-confidence rate, calibration metrics, coherence violations, and
delivery status.

`auto_publish` is allowed only when every blocking gate passes and no approval policy requires a
human. Delivery confirmation occurs after publication; delivery failure does not erase the
published version and instead creates a retryable delivery exception.

## P1 requirements

- Resume a run from the first uncommitted stage without recalculating earlier committed stages.
- Contract-configurable warning thresholds and exception aggregation by hierarchy node.
- A dry-run mode that resolves pins, eligibility counts, and planned writes without scoring.
- Operator commands to retry delivery, abandon a stale run, or supersede a draft with reasons.
- Extend the shipped FVA marts with optional component-level attribution between base,
  calibrated, and reconciled values. Benchmark, overridden, and published comparisons are already
  implemented in the [Forecast Operations spec](forecast_operations.md).

## P2 considerations

- Event-driven scoring in addition to cron schedules.
- Multiple publication destinations with independent delivery SLAs.
- Scenario forecasts sharing base evidence without competing with the operational publication.
- Distributed locking when orchestration spans more than one Prefect control plane.

## Persistence and lineage

The implementation may extend existing tables or add normalized stage tables, but it must expose
these logical records:

| Record | Purpose |
|--------|---------|
| forecast run | pinned inputs, logical identity, terminal state, counts |
| stage run | component input/output fingerprint, status, timing, error |
| base output | strategy-selected statistical forecast |
| calibrated output | quantiles and calibration lineage |
| reconciled output | coherent quantiles and hierarchy lineage |
| validation check | immutable gate result and severity |
| exception | scoped operational failure or warning |
| publication | immutable version and delivery state |
| status event | append-only transition audit |

Consumer views must join only a single successful `forecast_run_id` and `publication_version`.

## Success metrics

### Leading indicators

- 100% of scheduled contracts reach a terminal state with stage-level evidence.
- 100% of eligible entity/horizon keys appear in a draft, unless partial publication is explicitly
  enabled with a contract threshold of at least 99%.
- Zero duplicate canonical keys or mixed publication versions.
- 100% of visible hierarchical forecasts pass coherence and quantile-ordering gates.
- Retried identical runs create zero duplicate stage, output, or publication records.

### Lagging indicators

- At least 99% of scheduled drafts are ready within the contract publish-delay SLO.
- Fewer than 1% of publications require technical rollback, excluding business revisions.
- Median operator time to identify the failed stage is under ten minutes.

## Testing and validation

- Unit tests for run IDs, state transitions, locks, stage idempotency, and gate severity.
- Synthetic end-to-end fixture covering regular, intermittent, cold-start, and failed series.
- Property tests for nonnegative monotonic quantiles and hierarchy coherence.
- Failure tests for missing horizons, stale cutoffs, invalid artifacts, nonconvergent joint
  reconciliation, lost locks, and delivery errors.
- Retry test proving a failure after reconciliation resumes without duplicate earlier writes.
- dbt tests for one visible version per contract/origin and no consumer-visible nonterminal run.
- Live smoke test producing one traceable draft and one idempotent retry.

## Release acceptance criteria

- A scheduled run executes the authoritative stage order without retraining or changing champion.
- One complete canonical draft becomes atomically visible for the configured contract and origin.
- Every visible row is strategy-routed, calibrated, coherent when configured, provenance-complete,
  and traceable through component run IDs.
- Invalid, incomplete, incoherent, stale, or lock-losing runs cannot create a visible draft or
  publication.
- Identical retries do not duplicate output; changed material inputs create a new version.
- `draft_only`, `require_approval`, and `auto_publish` modes enforce their documented boundaries.

## Dependencies and sequencing

1. Extend the forecast run/output contracts for stage pins and atomic visibility.
2. Implement the pure in-memory pipeline and failure-path tests.
3. Add idempotent stage persistence and validation records.
4. Add Prefect orchestration, locking, and resume behavior.
5. Add dbt consumer, quality, and monitoring views.
6. Run local, then live draft-only acceptance before enabling approval or auto-publication.

## Current implementation

- The initial production contract publishes the governed horizon-7 champion and fails closed when
  prediction horizons do not match its contract.
- Prefect resolves the current champion, scores it without exposing the model writer's intermediate
  draft, and executes routing, split-conformal calibration, reconciliation/no-op reconciliation,
  and validation in the authoritative order.
- Logical run, stage, output, calibration, and validation IDs are deterministic. A BigQuery-backed
  lease prevents concurrent visibility for the same contract and origin.
- Stage evidence, blocking-gate evidence, and canonical output rows persist before the final
  `forecast_runs.run_status = 'draft'` record. `forecast_visible_drafts` enforces that atomic
  boundary for consumers.
- Failed logical runs persist retry-stable blocking exceptions without making partial output visible.
- Live draft-only execution and identical idempotent retries passed. The hierarchy-enabled path
  also persists separately queryable base/reconciled evidence and passed coherence, lineage, and
  fail-closed acceptance on 2026-08-10. Downstream delivery remains owned by its dedicated spec.

## Shipped evidence

This base pipeline is shipped. Live GCP acceptance persisted the authoritative five-stage order,
three passing blocking gates, one complete 54-row atomic draft, full component lineage, and no
duplicates after an identical retry. The accepted identifiers, results, defect history, and
verification SQL are recorded in
[scheduled forecast publication acceptance](../acceptance/scheduled_forecast_publication_2026-08-05.md).

## Open questions

- **Non-blocking — Data/operations:** tune default calibration-coverage and publish-delay
  thresholds after the first live draft-only runs.
- **Non-blocking — Platform:** choose the long-term lock backend; BigQuery-backed leases are
  acceptable for the first implementation.
- **Non-blocking — Product:** decide which contracts may opt into partial publication after full
  publication has operated successfully.

## Related documents

- [Forecast contract and canonical output](forecast_contract_and_output.md)
- [Forecasting methods](forecasting_methods.md)
- [Hierarchical reconciliation](hierarchical_reconciliation.md)
- [Forecast operations](forecast_operations.md)
- [Monitoring and SLOs](monitoring_and_slos.md)
- [Integration contracts](integration_contracts.md)

{% enddocs %}
