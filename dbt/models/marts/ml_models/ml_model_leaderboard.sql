{#
  Comparable BQML, Vertex holdout, and rolling-origin metrics.
  Champion consumers must use the full target/grain/horizon/segment/metric-policy key.
  See docs/specs/backtesting_and_model_lifecycle.md.
#}

{{ config(materialized='table', tags=['bqml', 'vertex', 'backtest']) }}

with vertex_leaderboard as (
    select
        'vertex' as platform,
        config_name,
        model_run_id,
        model_family,
        model_type,
        'demand_units' as target,
        case
            when model_family = 'favorita_store_daily' then 'store-day'
            else model_family
        end as grain,
        coalesce(
            safe_cast(regexp_extract(config_name, r'_h(\d+)_') as int64),
            safe_cast(regexp_extract(config_name, r'_n(\d+)d_') as int64)
        ) as horizon,
        '{}' as segment_key_json,
        case
            when model_family = 'favorita_store_daily' then 'wape'
            else 'mae'
        end as primary_metric,
        case
            when model_family = 'favorita_store_daily'
                then '{"evaluation_protocol":"holdout","primary_metric":"wape"}'
            else '{"evaluation_protocol":"holdout","primary_metric":"mae"}'
        end as metric_policy,
        run_at,
        mae,
        rmse,
        r2,
        wape,
        cast(null as float64) as mase,
        cast(null as float64) as rmsse,
        bias,
        cast(null as float64) as prediction_completeness
    from {{ ref('stg_vertex_model_performance') }}
    where metric_set = 'test'
),

{% if var('include_bqml_leaderboard', true) %}
bqml_leaderboard as (
    select
        'bqml' as platform,
        evaluate.model_name as config_name,
        cast(null as string) as model_run_id,
        'bqml' as model_family,
        'BOOSTED_TREE_REGRESSOR' as model_type,
        'demand_units' as target,
        'company-day' as grain,
        1 as horizon,
        '{}' as segment_key_json,
        'mae' as primary_metric,
        '{"evaluation_protocol":"holdout","primary_metric":"mae"}' as metric_policy,
        evaluate.evaluation_timestamp as run_at,
        evaluate.mean_absolute_error as mae,
        sqrt(evaluate.mean_squared_error) as rmse,
        evaluate.r2_score as r2,
        wape.wape,
        cast(null as float64) as mase,
        cast(null as float64) as rmsse,
        cast(null as float64) as bias,
        cast(null as float64) as prediction_completeness
    from {{ ref('bqml_model_evaluate') }} as evaluate
    left join {{ ref('int_bqml_model_wape') }} as wape
        on evaluate.model_name = wape.model_name
        and evaluate.run_date = wape.run_date
),
{% endif %}

backtest_leaderboard as (
    select
        'vertex' as platform,
        metrics.baseline_name as config_name,
        metrics.backtest_run_id as model_run_id,
        case
            when metrics.baseline_name = metrics.model_config_name then metrics.model_family
            else 'baseline'
        end as model_family,
        case
            when metrics.baseline_name = metrics.model_config_name then metrics.model_type
            else 'baseline'
        end as model_type,
        metrics.target,
        metrics.grain,
        metrics.horizon,
        metrics.segment_key_json,
        metrics.primary_metric,
        metrics.metric_policy_json as metric_policy,
        max(metrics.created_at) as run_at,
        safe_divide(sum(metrics.mae * metrics.eligible_count), sum(metrics.eligible_count)) as mae,
        cast(null as float64) as rmse,
        cast(null as float64) as r2,
        safe_divide(sum(metrics.wape * metrics.eligible_count), sum(metrics.eligible_count)) as wape,
        safe_divide(
            sum(metrics.mase * metrics.prediction_count),
            sum(if(metrics.mase is not null, metrics.prediction_count, 0))
        ) as mase,
        safe_divide(
            sum(metrics.rmsse * metrics.prediction_count),
            sum(if(metrics.rmsse is not null, metrics.prediction_count, 0))
        ) as rmsse,
        safe_divide(sum(metrics.bias * metrics.eligible_count), sum(metrics.eligible_count)) as bias,
        safe_divide(sum(metrics.prediction_count), sum(metrics.eligible_count)) as prediction_completeness
    from {{ ref('stg_backtest_metrics') }} as metrics
    group by
        metrics.baseline_name,
        metrics.backtest_run_id,
        metrics.model_config_name,
        metrics.model_family,
        metrics.model_type,
        metrics.target,
        metrics.grain,
        metrics.horizon,
        metrics.segment_key_json,
        metrics.primary_metric,
        metrics.metric_policy_json
),

unioned as (
    select * from vertex_leaderboard
    {% if var('include_bqml_leaderboard', true) %}
    union all
    select * from bqml_leaderboard
    {% endif %}
    union all
    select * from backtest_leaderboard
)

select
    *,
    to_hex(sha256(concat(
        target, '|', grain, '|', cast(horizon as string), '|',
        segment_key_json, '|', metric_policy
    ))) as comparable_partition_key
from unioned
where horizon is not null
