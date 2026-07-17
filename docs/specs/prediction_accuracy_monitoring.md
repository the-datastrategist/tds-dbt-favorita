{% docs spec_prediction_accuracy_monitoring %}

# SPEC: Prediction accuracy monitoring

**Status:** Proposed
**Roadmap reference:** [`client_rollout.md`](../client_rollout.md#post-rollout-weeks-58-optional) — "Drift / accuracy monitoring | dbt tests on prediction vs actual"

---

## Summary

`favorita_model_predictions` already stores `actual` alongside `prediction` per row ([`vertex/ddl/vertex_bq_tables.sql`](../../vertex/ddl/vertex_bq_tables.sql)), and [`benchmarks.md`](../benchmarks.md) already has a "Prediction vs actual" query recipe — but nothing runs on a schedule, and nothing fails loudly when accuracy degrades. This spec turns that ad hoc query into a dbt mart plus dbt tests that fail (or warn) when live accuracy drifts materially from the metrics recorded at training time.

## Problem

- Once a model is in production, its holdout metrics (`favorita_model_performance`, recorded once per training run) go stale — nothing re-checks whether *live* predictions still perform that well.
- `actual` in `favorita_model_predictions` is populated whenever the source join has ground truth available (see `build_standard_prediction_rows(..., actual_column=...)` in [`vertex/utils/predictions.py`](../../vertex/utils/predictions.py)) but for forward-looking forecasts (`forecast_horizon > 0`), `actual` is `NULL` until the forecasted date passes — so accuracy monitoring is naturally lagged and must tolerate partial data.
- There's no equivalent for BQML predictions/actuals — `bqml_model_predict` doesn't carry an `actual` column at all today.

## Goals

- A dbt mart computing rolling accuracy (MAE, WAPE, bias) per `config_name` / `model_type`, keyed by the date the *actual* became known, not the date the prediction was made.
- A dbt test that fails or warns when rolling accuracy is materially worse than the `test_performance` recorded at training time for the same `model_run_id`.
- Runs as part of a scheduled selector (extending `daily_refresh_tests`), so it surfaces without a human remembering to run `benchmarks.md`'s query recipe manually.

## Non-goals

- Feature/input drift (population stability index on the feature distributions feeding the model) — this spec is **prediction accuracy** (output vs. ground truth) only. A follow-on could reuse `top_feature_attributions` from [`stg_vertex_model_explain`](../../dbt/models/staging/stg_vertex_model_explain.sql) (shipped) to approximate feature-importance drift, but that's materially harder to make robust and is deferred.
- Automated retraining or alerting integration (PagerDuty/Slack) — this spec produces a **queryable/testable signal**; wiring it to a notification channel is a Prefect/ops follow-on (see `orchestration/README.md`).
- BQML accuracy monitoring — `bqml_model_predict` has no `actual` column; adding one is a prerequisite not covered here (see Open questions).

## Design

### 1. Intermediate model: `int_vertex_prediction_accuracy_daily`

One row per `(config_name, model_type, forecast_date)`, aggregating `stg_vertex_model_predictions` rows where `actual is not null`:

```sql
{% raw %}{{ config(materialized='incremental', unique_key=['config_name', 'forecast_date'], partition_by={'field': 'forecast_date', 'data_type': 'date'}) }}

select
    config_name,
    model_family,
    model_type,
    model_run_id,
    forecast_date,
    count(*) as n_predictions,
    avg(abs(actual - prediction)) as mae,
    sum(abs(actual - prediction)) / nullif(sum(abs(actual)), 0) as wape,
    avg(prediction - actual) as bias
from {{ ref('stg_vertex_model_predictions') }}
where actual is not null
group by config_name, model_family, model_type, model_run_id, forecast_date{% endraw %}
```

`forecast_date` (not `run_date`) is the grouping key: a prediction made on day T for T+7 only becomes checkable on T+7 once `actual` lands, so this table is inherently append-only as actuals arrive, matching the existing `insert_overwrite` staging pattern used elsewhere in this project.

### 2. Rolling window mart: `favorita_prediction_accuracy_rolling`

7-day and 28-day trailing MAE/WAPE per `config_name`, plus the `model_run_id`'s original `test_performance` for comparison:

```sql
{% raw %}select
    a.config_name,
    a.model_run_id,
    a.forecast_date,
    avg(a.mae) over (
        partition by a.config_name order by a.forecast_date
        rows between 6 preceding and current row
    ) as mae_7d,
    avg(a.wape) over (
        partition by a.config_name order by a.forecast_date
        rows between 6 preceding and current row
    ) as wape_7d,
    p.mae as train_test_mae,
    p.wape as train_test_wape
from {{ ref('int_vertex_prediction_accuracy_daily') }} a
left join {{ ref('stg_vertex_model_performance') }} p   -- from the leaderboard mart spec
    on a.model_run_id = p.model_run_id{% endraw %}
```

Depends on `stg_vertex_model_performance`, introduced in the [model leaderboard mart spec](model_leaderboard_mart.md) — sequence that spec first, or inline a minimal version here if it ships independently.

### 3. Drift test

A singular dbt test (`tests/singular/assert_no_material_accuracy_drift.sql`) flags rows where live WAPE has degraded beyond a tolerance vs. training-time WAPE:

```sql
{% raw %}select *
from {{ ref('favorita_prediction_accuracy_rolling') }}
where train_test_wape is not null
  and wape_7d > train_test_wape * (1 + {{ var('accuracy_drift_tolerance_pct', 0.25) }}){% endraw %}
```

Configured via `config(severity='warn')` initially (avoid blocking `dbt build` on a monitoring signal that hasn't been tuned yet); promote to `error` once tolerance thresholds are validated against real client data. `accuracy_drift_tolerance_pct` as a `dbt_project.yml` var makes the threshold overridable per client/engagement.

### 4. Scheduling

Add to `dbt/selectors.yml` as `daily_refresh_tests` additions, or a new selector `accuracy_monitoring` run on its own cadence (e.g. daily, after `stg_vertex_model_predictions` refresh) — matches the existing `selector-daily-refresh-test` Makefile pattern:

```yaml
# dbt/selectors.yml
accuracy_monitoring:
  definition:
    method: fqn
    value: favorita_prediction_accuracy_rolling
    children: true
```

```makefile
selector-accuracy-monitoring: ## Run prediction-accuracy drift tests
	docker compose run --rm ml-pipeline dbt build --project-dir dbt --target $(DBT_TARGET) --selector accuracy_monitoring $(ARGS)
```

## Testing & validation

- Unit-test the WAPE/MAE SQL logic against a small seed fixture (2–3 configs, a few forecast dates, known actual/prediction pairs) using dbt unit tests (`dbt/models/staging/schema.yml` pattern — see `using-dbt-for-analytics-engineering`/`adding-dbt-unit-test` skills already available in this environment).
- Validate against a real backfill (`make vertex-backfill`) before trusting the drift test in production — backfilled predictions with known actuals are the best available "ground truth for the ground-truth checker."

## Open questions

- Should BQML get an `actual` column added to `bqml_model_predict` (join back to `int_sales_daily` by date) so it's covered by the same monitoring, or is BQML out of scope for monitoring long-term since Vertex is the primary path for engagements that need this?
- Is 25% WAPE degradation the right default tolerance, or should it be metric-set-specific (tighter for `mae`, looser for `wape` on sparse/intermittent grains)? No data yet to calibrate — ship with a conservative default and revisit per client.

## Related documents

- [Specs index](README.md)
- [Model leaderboard mart](model_leaderboard_mart.md) — provides `stg_vertex_model_performance`
- [Benchmarks](../benchmarks.md) — existing manual "prediction vs actual" query this automates
- [IaC — monitoring](../iac.md#monitoring)

{% enddocs %}
