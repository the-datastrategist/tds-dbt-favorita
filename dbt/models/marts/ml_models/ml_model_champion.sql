{# Current champion inside each semantically comparable forecast partition. #}

{{ config(materialized='table', tags=['bqml', 'vertex', 'backtest']) }}

with latest_run_per_candidate as (
    select
        *,
        row_number() over (
            partition by
                target, grain, horizon, segment_key_json, metric_policy,
                platform, config_name
            order by run_at desc, model_run_id desc
        ) = 1 as is_latest_run
    from {{ ref('ml_model_leaderboard') }}
),

ranked as (
    select
        *,
        case primary_metric
            when 'wape' then wape
            when 'mae' then mae
        end as primary_metric_value
    from latest_run_per_candidate
    where is_latest_run
),

champion as (
    select
        *,
        row_number() over (
            partition by target, grain, horizon, segment_key_json, metric_policy
            order by primary_metric_value asc nulls last, platform, config_name
        ) = 1 as is_champion
    from ranked
)

select
    platform,
    config_name,
    model_run_id,
    model_family,
    model_type,
    target,
    grain,
    horizon,
    segment_key_json,
    primary_metric,
    metric_policy,
    comparable_partition_key,
    run_at,
    mae,
    rmse,
    r2,
    wape,
    bias,
    prediction_completeness,
    primary_metric_value,
    is_champion
from champion
