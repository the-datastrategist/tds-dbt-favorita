{% docs spec_model_leaderboard_mart %}

# SPEC: Model leaderboard mart

**Status:** Proposed
**Roadmap reference:** [`client_rollout.md`](../client_rollout.md#post-rollout-weeks-58-optional) — "Model leaderboard mart | `favorita_model_performance` + dbt mart"; [`delivery_artifacts.md`](../delivery_artifacts.md#dashboard-blueprint) dashboard page 3 "Model leaderboard"

---

## Summary

Today, comparing BQML and Vertex models means manually filling in `{fill}` placeholders in [`benchmarks.md`](../benchmarks.md) by hand-copying query output. This spec adds a dbt mart that automatically unions holdout metrics from both platforms into one ranked table with a `is_champion` flag, so benchmarking and champion selection are queries, not spreadsheets.

## Problem

- `favorita_model_performance` (Vertex holdout metrics: mae, rmse, wape, r2, ...) has **no staging model** yet — it's declared as a source in [`dbt/models/sources/vertex.yml`](../../dbt/models/sources/vertex.yml) but, unlike `favorita_model_predictions`/`favorita_model_metadata`, there is no `stg_vertex_model_performance.sql`.
- BQML's `bqml_model_evaluate` mart ([`dbt/models/marts/ml_models/bqml_model_evaluate.sql`](../../dbt/models/marts/ml_models/bqml_model_evaluate.sql)) returns whatever columns `ML.EVALUATE()` emits for the model type (`mean_absolute_error`, `mean_squared_error`, `r2_score`, ... for `BOOSTED_TREE_REGRESSOR`) — not the same column names as Vertex's `mae`/`rmse`/`wape`.
- There is consequently **no single query** that ranks BQML vs. Vertex vs. model family/config, and champion selection (`benchmarks.md` § "Champion selection") is a manual judgment call with no persisted audit trail of *when* a champion changed.

## Goals

- One row per (platform, config_name, run) with a **normalized metric set** (mae, rmse, wape, r2 where available).
- A boolean `is_champion` per grain (e.g. store-day vs. company-day), computed from the latest run per config, ranked by a configurable primary metric.
- Feed [`benchmarks.md`](../benchmarks.md) "Champion selection" and the dashboard blueprint's "Model leaderboard" page directly from this mart instead of manual fill-in.
- Preserve champion history (don't overwrite — append-only or snapshot) so "when did the champion change" is answerable.

## Non-goals

- Automatically promoting a new champion into production scoring — this spec only *identifies* the champion; wiring predict jobs to always use "the champion config" is a separate, later change.
- Backfilling WAPE for historical BQML `ML.EVALUATE` runs — `ML.EVALUATE` doesn't return WAPE natively (see below); this spec computes it going forward only, from `bqml_model_predict` actuals.

## Design

### 1. New staging model: `stg_vertex_model_performance`

Mirrors the existing pattern in [`stg_vertex_model_predictions.sql`](../../dbt/models/staging/stg_vertex_model_predictions.sql) / [`stg_vertex_model_explain.sql`](../../dbt/models/staging/stg_vertex_model_explain.sql):

```sql
{% raw %}{{ config(materialized='view', tags=['vertex', 'staging']) }}

select
    model_run_id,
    model_id,
    config_name,
    model_family,
    model_type,
    run_at,
    metric_set,
    mean_pred,
    mean_actual,
    mae,
    rmse,
    mse,
    r2,
    mape,
    wape,
    smape,
    bias,
    median_ae
from {{ source('vertex_ml', 'favorita_model_performance') }}{% endraw %}
```

Add `dbt/models/staging/schema.yml` column docs + `not_null` tests on `model_run_id`, `model_id`, `config_name`. Note in the description that `metric_set` is currently always `'test'` (see [`vertex/utils/metadata.py`](../../vertex/utils/metadata.py) `performance_row_from_metadata`, called with `metric_set="test"` from all three train scripts) — `'train'` metrics exist in `favorita_model_metadata.train_performance` (JSON) but aren't written to `favorita_model_performance` today. Out of scope here; flag as a follow-on if train-vs-test comparison becomes a need.

### 2. Normalize BQML metrics to the same shape

`ML.EVALUATE` for `BOOSTED_TREE_REGRESSOR` returns `mean_absolute_error`, `mean_squared_error`, `mean_squared_log_error`, `median_absolute_error`, `r2_score`, `explained_variance` — no WAPE. Two options, pick (b):

- (a) Leave `wape` null for BQML rows in the leaderboard — simplest, but `benchmarks.md`'s company-day champion is selected on `test_mae`, so this is workable for that grain but not comparable to Vertex's WAPE-based store-day selection.
- (b) **Compute WAPE for BQML from `bqml_model_predict`** (`SUM(ABS(actual - prediction)) / SUM(ABS(actual))`), joined by `run_date`/`model_name`, in a small intermediate model `int_bqml_model_wape.sql`. This makes BQML and Vertex genuinely comparable on the metric `benchmarks.md` already recommends as the primary store/company-day metric.

### 3. Mart: `favorita_model_leaderboard`

New model in `dbt/models/marts/ml_models/favorita_model_leaderboard.sql` (materialized `table`, tagged `bqml, vertex` — depends on both), unioning:

| Column | From Vertex (`stg_vertex_model_performance`) | From BQML (`bqml_model_evaluate` + `int_bqml_model_wape`) |
|--------|-----------------------------------------------|-------------------------------------------------------------|
| `platform` | `'vertex'` | `'bqml'` |
| `config_name` | `config_name` | `model_name` |
| `model_family` | `model_family` | `'bqml'` (or `metric` — see open question) |
| `model_type` | `model_type` | `'BOOSTED_TREE_REGRESSOR'` (static today; `model_configs` var has no `model_type` lookup at evaluate-time, so hardcode until `bqml_model_evaluate` carries it through) |
| `grain` | derived: `case when model_family = 'favorita_store_daily' then 'store-day' else model_family end` | derived from `interval`/`metric` (`'company-day'` today) |
| `run_at` | `run_at` | `evaluation_timestamp` |
| `mae` | `mae` | `mean_absolute_error` |
| `rmse` | `rmse` | `sqrt(mean_squared_error)` |
| `r2` | `r2` | `r2_score` |
| `wape` | `wape` | from `int_bqml_model_wape` |

### 4. Champion flag model: `favorita_model_champion`

```sql
{% raw %}select
    *,
    row_number() over (
        partition by grain
        order by run_at desc
    ) = 1 as is_latest_run,
    row_number() over (
        partition by grain, is_latest_run
        order by
            case grain
                when 'store-day' then wape
                else mae
            end asc
    ) = 1 and is_latest_run as is_champion
from {{ ref('favorita_model_leaderboard') }}{% endraw %}
```

Primary metric per grain matches `benchmarks.md`'s existing recommendation (`test_wape` for store-day, `test_mae` for company-day) — expose as a dbt var (`leaderboard_primary_metric_by_grain`) rather than hardcoding, so a client engagement can override it.

### 5. Tests

- `not_null` on `platform`, `config_name`, `grain`, `run_at`.
- `accepted_values` on `platform`: `['bqml', 'vertex']`.
- Singular test `assert_at_most_one_champion_per_grain.sql`: `having count(*) > 1` where `is_champion` grouped by `grain` should return zero rows.

## Implementation plan

1. `stg_vertex_model_performance` + schema/tests (small, unblocks everything else).
2. `int_bqml_model_wape` (BQML WAPE calc from predict/actuals).
3. `favorita_model_leaderboard` union mart.
4. `favorita_model_champion` + singular test.
5. Update `benchmarks.md` "Champion selection" section to a query against `favorita_model_champion` instead of a manually filled table; update `delivery_artifacts.md` dashboard blueprint's leaderboard page source to `favorita_model_champion`.
6. Add `favorita_model_leaderboard` / `favorita_model_champion` to `dbt/models/exposures.yml` if/when a dashboard consumes them.

## Open questions

- `model_family` for BQML rows: `model_configs` in `dbt_project.yml` doesn't currently have a `model_family` field (it has `metric`, `interval`, `model_name`) — either add one to `model_configs`, or accept `'bqml'` as a coarse stand-in until multiple BQML configs with different grains exist.
- Should `favorita_model_champion` be `materialized='table'` (snapshot per run) or an actual dbt `snapshot` (full history via `dbt snapshot`)? A snapshot gives "when did the champion change" for free via `dbt_valid_from`/`dbt_valid_to`; a table only shows the current champion. Recommend snapshot if champion-change history becomes a client deliverable.

## Related documents

- [Specs index](README.md)
- [Benchmarks](../benchmarks.md)
- [Delivery artifacts — dashboard blueprint](../delivery_artifacts.md#dashboard-blueprint)
- [Client rollout](../client_rollout.md)

{% enddocs %}
