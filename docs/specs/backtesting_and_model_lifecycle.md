{% docs spec_backtesting_and_model_lifecycle %}

# SPEC: Rolling-origin backtesting and model lifecycle

**Status:** Proposed
**Roadmap reference:** [`demand_forecasting_platform_recommendations.md`](../demand_forecasting_platform_recommendations.md) — P0 "Replace the single holdout with rolling-origin backtesting" and "Fix model benchmark and champion semantics"

---

## Summary

The current benchmark and leaderboard path compares recent holdout metrics from BQML and Vertex runs. That is useful for an accelerator, but an end-to-end demand forecasting platform needs rolling-origin backtests, comparable baseline models, horizon-specific metrics, and explicit model lifecycle states.

This spec adds `docs/backtesting_and_evaluation.md`, a reusable backtest runner, baseline models, corrected leaderboard keys, and gated champion promotion.

## Goals

- Evaluate forecasts over multiple historical origins using the same horizons and feature availability rules as production scoring.
- Add naive and demand-specific baselines to every benchmark.
- Store metrics by target, grain, horizon, segment, model, baseline, and forecast contract.
- Replace direct cross-grain ranking with comparable leaderboard keys.
- Add model lifecycle states: `candidate`, `challenger`, `champion`, `archived`, `rejected`.
- Require promotion gates before a model becomes champion.

## Non-goals

- Fully automated deployment of a new champion into all downstream systems. This spec records and gates champion decisions; publishing behavior belongs in [forecast operations](forecast_operations.md).
- Human approval UI. The lifecycle tables should support approval, but UI belongs in a later planner workflow.
- Feature leakage detection implementation. Backtests consume the point-in-time registry from [point-in-time feature availability](point_in_time_feature_availability.md).

## Design

### 1. Documentation

Add `docs/backtesting_and_evaluation.md` covering:

- rolling-origin evaluation concepts
- cutoff/origin terminology
- baseline definitions
- horizon-specific metrics
- promotion gates
- why R2 is not a primary demand forecasting selection metric

### 2. Backtest runner

Add a reusable runner under `vertex/jobs/backtest.py` or `forecasting_core/backtesting/`.

Inputs:

- forecast contract name/path
- model config name
- origin date list or generation policy
- horizon list
- segment columns
- max entities for dev runs
- output dataset/table

The runner should:

1. Build training data using only rows available at each origin.
2. Train or load the candidate model per origin.
3. Score every required horizon.
4. Score baselines on the same target/grain/horizons.
5. Write immutable run and metric rows.

### 3. Baseline models

Implement baselines that require no Vertex model artifact:

| Baseline | Description |
|----------|-------------|
| `zero_demand` | Predict zero |
| `last_observation` | Most recent observed demand before origin |
| `seasonal_naive_7d` | Same weekday last week |
| `same_period_last_year` | Same date/week last year, when sufficient history exists |
| `moving_average` | Configurable trailing window |
| `croston_sba_tsb` | Intermittent-demand baseline family |

Baselines should write to the same metric tables as ML models with `model_type = baseline`.

### 4. Metrics

Store metrics at minimum:

- WAPE
- MAE
- MASE or RMSSE
- bias / mean error
- pinball loss for quantiles
- interval coverage and interval width
- prediction completeness

Metric rows must include:

```text
forecast_contract_name
forecast_contract_hash
target
grain
horizon
segment_key_json
model_type
model_config_name
model_run_id
baseline_name
origin_start
origin_end
metric_name
metric_value
created_at
```

### 5. Comparable leaderboard keys

Update leaderboard marts so champion selection partitions by:

```text
target × grain × horizon × segment × metric_policy
```

Do not compare company-day BQML and store-day Vertex runs as substitutes unless they are explicitly rolled up/down to the same target/grain/horizon.

### 6. Lifecycle and promotion gates

Add model lifecycle tables:

| Table | Purpose |
|-------|---------|
| `model_candidates` | Candidate/challenger metadata |
| `model_lifecycle_events` | State transitions with actor, reason, and evidence |
| `model_promotion_checks` | Gate results for each candidate |

Promotion gates:

- beats appropriate naive baseline by configured margin
- no material regression by critical segment or horizon
- acceptable bias
- acceptable interval coverage when quantiles are present
- complete predictions for eligible entities
- reproducible artifact, config hash, feature version, and code SHA
- optional human approval

## Implementation plan

1. Add `docs/backtesting_and_evaluation.md`.
2. Add backtest runner CLI and config plumbing.
3. Implement baseline scorers and unit tests.
4. Add BigQuery DDL for backtest runs, metrics, lifecycle, and promotion checks.
5. Add dbt staging models and revised leaderboard/champion marts.
6. Update `docs/benchmarks.md` to query backtest and lifecycle tables.
7. Add Prefect flow for scheduled or manual backtesting.

## Testing & validation

- Unit tests for each baseline on small deterministic series.
- Backtest dry-run that emits generated SQL and origin plan.
- Small synthetic backtest with two origins and two horizons.
- dbt tests ensuring at most one champion per comparable key.
- Regression test that BQML company-day and Vertex store-day do not compete in the same champion partition.

## Acceptance criteria

- A rolling-origin benchmark can compare at least one ML model and three baselines at the same grain/horizon.
- Champion rows are keyed by target, grain, horizon, segment, and metric policy.
- A candidate cannot become champion unless promotion checks pass or are explicitly waived with an audit reason.

## Related documents

- [Forecast contract and canonical output](forecast_contract_and_output.md)
- [Point-in-time feature availability](point_in_time_feature_availability.md)
- [Forecasting methods](forecasting_methods.md)
- [Prediction accuracy monitoring](prediction_accuracy_monitoring.md)

{% enddocs %}
