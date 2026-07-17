{#
  Unified BQML + Vertex holdout metrics, normalized to a shared column set, so benchmarking
  and champion selection (favorita_model_champion) are queries instead of hand-filled tables.
  See docs/specs/model_leaderboard_mart.md.
#}

{{ config(
    materialized='table',
    tags=['bqml', 'vertex'],
) }}

with vertex_leaderboard as (
    select
        'vertex' as platform,
        config_name,
        model_run_id,
        model_family,
        model_type,
        case
            when model_family = 'favorita_store_daily' then 'store-day'
            else model_family
        end as grain,
        run_at,
        mae,
        rmse,
        r2,
        wape
    from {{ ref('stg_vertex_model_performance') }}
    where metric_set = 'test'
),

bqml_evaluate as (
    select
        model_name,
        run_date,
        evaluation_timestamp,
        mean_absolute_error,
        mean_squared_error,
        r2_score
    from {{ ref('bqml_model_evaluate') }}
),

bqml_leaderboard as (
    select
        'bqml' as platform,
        e.model_name as config_name,
        cast(null as string) as model_run_id,
        'bqml' as model_family,
        -- Static today: model_configs has no model_type lookup carried through
        -- bqml_model_evaluate's ML.EVALUATE output; hardcode until it does.
        'BOOSTED_TREE_REGRESSOR' as model_type,
        'company-day' as grain,
        e.evaluation_timestamp as run_at,
        e.mean_absolute_error as mae,
        sqrt(e.mean_squared_error) as rmse,
        e.r2_score as r2,
        w.wape
    from bqml_evaluate e
    left join {{ ref('int_bqml_model_wape') }} w
        on e.model_name = w.model_name
        and e.run_date = w.run_date
)

select platform, config_name, model_run_id, model_family, model_type, grain, run_at, mae, rmse, r2, wape
from vertex_leaderboard

union all

select platform, config_name, model_run_id, model_family, model_type, grain, run_at, mae, rmse, r2, wape
from bqml_leaderboard
