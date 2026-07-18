# Demand Forecasting Platform: Implementation Recommendations

## Purpose

This document turns the architecture review into an implementation roadmap for evolving this repository into a production-style GCP demand forecasting platform.

The existing foundation is strong: dbt-based features, BigQuery ML and Vertex model paths, experiment tracking, orchestration, CI, and GCP IaC. The principal gap is between producing a prediction and enabling a planner or downstream system to make an auditable operating decision from it.

## Reuse model

The platform is intentionally **GCP-only**. BigQuery, GCS, Vertex AI, Artifact Registry, Cloud Scheduler / Workflows patterns, and Terraform-managed GCP infrastructure are part of the product boundary.

Reuse across projects comes from contracts, conventions, and operating patterns:

- forecast contracts
- canonical forecast output and publication semantics
- evaluation and promotion rules
- model metadata and artifact tracking
- orchestration, monitoring, and SLO patterns
- dbt documentation, tests, lineage, and exposure conventions

Each implementation is expected to create its own dbt project or dbt model layer aligned to its source systems and planning use case. That dbt layer is the canonical adapter from raw business data into forecast-ready features. This is intentional: demand forecasting features vary by industry, inventory availability, promotion planning process, entity hierarchy, and target definition.

Formal third-party plugin / connector interfaces are out of scope for now. New projects should adapt the dbt layer and platform configuration directly.

## Product boundary

The platform should support the full lifecycle:

1. Ingest demand, inventory, pricing, promotion, calendar, and master data.
2. Validate and construct point-in-time-correct features.
3. Backtest and select models by comparable forecasting problem.
4. Generate versioned, multi-horizon probabilistic forecasts.
5. Reconcile forecasts across business hierarchies.
6. Monitor data, pipeline, forecast, and business health.
7. Allow planner review, adjustment, approval, and publication.
8. Deliver approved forecasts to BI, APIs, and planning/replenishment consumers.
9. Learn from actuals and planner overrides.

The current repository substantially covers steps 1-4 for a project implementation. The work below fills in the remaining platform capabilities and makes the existing behavior explicit.

## P0 — Forecasting-engine foundations

Complete these first. They establish a reliable, comparable, and extensible forecasting engine.

### 1. Introduce a forecast contract

Create `docs/forecast_contract.md` and a validated configuration schema. Every forecast configuration must specify:

- target metric and unit (`demand_units`, `sales_revenue`, etc.)
- entity grain and hierarchy
- time frequency and business timezone
- issue schedule / forecast origin
- forecast horizons
- training-window policy
- eligible entity rules
- known-future versus observed covariates
- quantiles requested
- model and feature versions
- reconciliation policy

Suggested configuration shape:

```yaml
forecast:
  target: demand_units
  dimensions: [store_id, product_id]
  frequency: day
  timezone: America/Guayaquil
  issue_schedule: "0 6 * * *"
  horizons: [1, 2, 3, 4, 5, 6, 7, 14, 28]
  quantiles: [0.1, 0.5, 0.9]
  training_window_days: 730
  known_future_features: [promotion, holiday, planned_price]
  observed_features: [sales, transactions, inventory_on_hand]
  hierarchy: [company, store, product_family, product]
```

Implement one canonical forecast-output table. It should include:

- `forecast_run_id`, `forecast_origin`, `target_date`, `horizon`
- entity keys and grain
- `prediction_p10`, `prediction_p50`, `prediction_p90` (or a normalized quantile child table)
- statistical forecast, planner override, approved forecast, and final published forecast
- model version, feature version, code SHA, and data cutoff
- status: `draft`, `approved`, `published`, `superseded`, `failed`

### 2. Implement multi-horizon forecasting

Document and implement the chosen multi-step strategy: recursive, direct, multi-output, or global model. Forecasts must be evaluated and published by horizon, not only by target date.

The default `n1d` configuration should either be explicitly defined as a one-day model or replaced/extended with a horizon-aware configuration. Do not claim one-week forecasting unless every required horizon is generated and evaluated.

### 3. Replace the single holdout with rolling-origin backtesting

Create `docs/backtesting_and_evaluation.md` and a reusable backtest runner.

Requirements:

- multiple historical cutoff dates
- same forecast horizon set and feature availability rules used in production
- results at entity, segment, hierarchy, horizon, and aggregate levels
- immutable records of the cutoff, configuration, model version, and metrics
- no leakage: only data available at each cutoff may be used

Add baseline models to every benchmark:

- zero demand
- last observation
- seasonal naive (same weekday last week)
- same period last year, where sufficient history exists
- moving average
- Croston/SBA/TSB for intermittent series

Primary metrics:

- WAPE / MAE for aggregate business performance
- MASE or RMSSE for comparison across series
- bias / mean error
- pinball loss for quantiles
- interval coverage and width
- business-cost or service-level metric when inventory data exists

Do not use R2 as a primary model-selection metric for demand forecasting.

### 4. Fix model benchmark and champion semantics

Update the leaderboard key to at least:

```text
target × grain × horizon × segment × metric policy
```

Do not rank company-day BQML and store-day Vertex models against each other as direct substitutes. They solve different forecasting problems.

Implement model lifecycle states:

- candidate
- challenger
- champion
- archived
- rejected

Champion promotion gates should require:

- statistically/business-meaningful improvement over the appropriate baseline
- no material regression for important segments or horizons
- acceptable bias and interval coverage
- successful data-quality and prediction-completeness checks
- reproducible model artifact, feature definition, and code version
- optional human approval

### 5. Enforce point-in-time feature correctness

Create a feature-availability registry that marks each feature as:

- observed only after the target period
- known in advance
- forecasted external input
- planned but subject to revision

Backtests must use the same information set that would have existed at the historical forecast origin. Add automated leakage tests and record the latest source timestamp used in every forecast run.

## P1 — Production forecast capabilities

### 6. Add probabilistic forecasts

Generate calibrated P10/P50/P90 forecasts, or configurable quantiles. Support at least one model-family-native path and a model-agnostic conformal prediction path.

Track pinball loss, coverage, and interval width by horizon and segment. Use the resulting uncertainty for scenario, service-level, and safety-stock consumers.

### 7. Add hierarchical reconciliation

Create `docs/hierarchical_reconciliation.md` and a hierarchy configuration model.

Implement selectable reconciliation methods:

- bottom-up
- top-down
- middle-out
- MinT / variance-weighted reconciliation

Guarantee that published forecasts reconcile across company, store, family, and SKU levels. Distinguish clearly between independently trained models at several grains and reconciled forecasts at several grains.

### 8. Handle demand-specific data conditions

Create `docs/demand_data_model.md`. Explicitly distinguish observed sales from unconstrained demand.

Add interfaces and policies for:

- inventory on hand and in-stock status
- stockouts and censored/lost demand
- store closures
- product launch, assortment, retirement, and eligibility dates
- price and promotion history/plans
- supplier and capacity constraints where available

For implementations without stock/availability data, state plainly that the system forecasts observed sales as a proxy for demand and does not estimate unconstrained demand.

### 9. Add cold-start and intermittent-demand routing

Classify series by history length and demand intermittency. Implement an explicit fallback hierarchy:

1. Entity-specific model where sufficient history exists.
2. Global model using product/store attributes.
3. Family/store-level forecast allocated to the entity.
4. Seasonal/rate-based baseline.
5. Configured business default with a low-confidence flag.

Persist the selected strategy on each forecast row.

### 10. Separate daily scoring from retraining and tuning

Define an operating cadence:

- daily: ingest, validate, score the active champion, publish forecasts, monitor
- weekly or trigger-based: retrain challengers
- monthly or trigger-based: hyperparameter optimization
- gated: promotion to champion

Add runbooks for retries, partial failures, backfills, forecast revision, and champion rollback.

### 11. Expand monitoring and SLOs

Create `docs/monitoring_and_slos.md` and Terraform-managed alerts for:

- pipeline success, duration, retries, and cost
- source freshness and late-arriving data
- feature completeness and schema changes
- eligible-entity and prediction coverage
- stale/missing forecast publication
- forecast error, bias, and calibration by horizon/segment
- feature and target drift
- regression versus naive baseline and current champion

Define SLOs for forecast freshness, completeness, pipeline availability, and maximum publish delay. Route alerts to a configurable notification destination.

## P2 — Planning and decision workflow

### 12. Build a forecast operations layer

A forecast-vs-actual dashboard is observability, not planning. Add a planner workflow with:

- exception queue based on business impact and uncertainty
- drill-down by entity, hierarchy, horizon, and drivers
- manual overrides, comments, reason codes, and audit trail
- bulk adjustment/import/export
- approval and freeze windows
- forecast version comparison
- publication status and downstream-delivery confirmation

Keep these values separately:

- statistical forecast
- planner override
- approved consensus forecast
- published forecast
- actual outcome

Measure Forecast Value Added (FVA) to establish whether overrides improve accuracy or business outcomes.

### 13. Add scenario planning

Support scenario-specific known-future inputs such as planned price, promotion, campaign, store closure, assortment, and weather/event assumptions. A scenario must produce a versioned forecast without overwriting the baseline forecast.

### 14. Publish through a standard integration contract

Create `docs/integration_contracts.md`. Expose standard consumption paths:

- canonical BigQuery tables/views
- batch export command
- forecast retrieval API
- override, approval, and publication APIs
- event/webhook on successful publication
- examples for replenishment, purchasing, staffing, ERP, and BI consumers

Minimum API concepts:

```text
GET  /v1/forecasts
POST /v1/overrides
POST /v1/forecast-runs/{run_id}/approve
POST /v1/forecast-runs/{run_id}/publish
```

All publish operations should be idempotent and retrieve forecasts by explicit version/run ID.

## P3 — Open-source product readiness

### 15. Separate platform contracts from project implementations

Refactor toward a layout such as:

```text
forecasting_core/       Generic contracts, evaluation, reconciliation, lifecycle
examples/               Project implementations and demo datasets
deploy/gcp/             Terraform and GCP deployment modules
ui/                     Planner and monitoring application
docs/                   Product and contributor documentation
```

Project-specific table names, service accounts, models, and configuration should live inside project implementations rather than define the core platform identity.

### 16. Add community and release governance

Add:

- `LICENSE`
- `CONTRIBUTING.md`
- `CODE_OF_CONDUCT.md`
- `SECURITY.md`
- issue and PR templates
- support policy
- semantic versioning and release process
- public roadmap
- architectural decision records
- compatibility matrix for Python, dbt, BigQuery, Vertex, and optional dependencies
- migration guides for breaking config/schema changes
- extension guide for model families, dbt project implementations, and forecast destinations

### 17. Make the first-run experience self-contained

Provide:

- a one-command quickstart using synthetic data or automated public-data download
- a completed reference benchmark, not only empty templates
- expected output examples
- local-only and GCP deployment paths
- estimated costs and cleanup/teardown instructions
- CI smoke tests that exercise the primary path without client credentials

## Required documentation deliverables

Create the following documents as part of implementation:

| Document | Purpose |
|---|---|
| `forecast_contract.md` | Forecast schema, versioning, horizons, quantiles, eligibility, and status lifecycle |
| `backtesting_and_evaluation.md` | Rolling-origin evaluation, baselines, metrics, and promotion gates |
| `forecasting_methods.md` | Global/local methods, multi-horizon strategy, intermittent demand, and cold start |
| `hierarchical_reconciliation.md` | Hierarchy definition, reconciliation options, and coherent-output guarantee |
| `demand_data_model.md` | Sales versus demand, inventory/availability, lifecycle, and future covariates |
| `forecast_operations.md` | Score, review, override, approve, publish, revise, backfill, and rollback workflows |
| `monitoring_and_slos.md` | Data/model/forecast/pipeline monitoring and operational objectives |
| `integration_contracts.md` | Warehouse, API, export, webhook, and delivery contracts |
| `open_source_governance.md` | Contribution, security, releases, compatibility, and extension policy |
| `product_roadmap.md` | Implemented, in-progress, experimental, planned, and consulting-only scope |

## Suggested acceptance criteria

The platform should not be labeled end-to-end until it can demonstrate all of the following on a project implementation or synthetic reference dataset:

- A versioned 7-, 14-, or 28-day forecast is generated from a documented forecast contract.
- Every prediction identifies its forecast origin, horizon, model version, feature version, and data cutoff.
- A rolling-origin benchmark compares the champion with appropriate naive baselines at the same target/grain/horizon.
- Published forecasts include calibrated uncertainty intervals.
- Published SKU forecasts reconcile to family, store, and company totals.
- Data/pipeline/forecast health checks detect missing data, stale forecasts, coverage failures, and material bias/degradation.
- The system can rerun a historical forecast using its recorded code/config/data inputs.
- A planner can review an exception, enter an auditable override, approve it, and publish the resulting version.
- A downstream consumer can retrieve an explicit published forecast version through a documented table, export, or API.
- A new contributor can run the example, inspect output, and submit an extension using documented project conventions.

## Recommended implementation order

1. Forecast contract and canonical output tables.
2. Multi-horizon scoring and rolling-origin backtesting.
3. Baselines, comparable leaderboard keys, and gated champion promotion.
4. Point-in-time feature availability and demand-data model.
5. Quantiles, calibration, and monitoring/SLOs.
6. Hierarchical reconciliation and intermittent/cold-start routing.
7. Scheduler redesign, backfill/rollback tooling, and publication contract.
8. Planner workflow, overrides, approval, and scenario planning.
9. Platform-contract / project-implementation separation and open-source governance.

## Scope clarification

Until the demand-data and decision-workflow capabilities are implemented, describe the repository as:

> A production-style GCP demand forecasting platform.

After the P0 and P1 work is complete, it can credibly be described as a demand forecasting engine with stronger reusable contracts. After P2 is complete, it is an end-to-end demand forecasting platform.
