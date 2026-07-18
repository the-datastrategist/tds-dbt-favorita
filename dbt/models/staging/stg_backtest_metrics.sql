{{ config(materialized='view', tags=['vertex', 'staging', 'backtest']) }}

select
    metrics.metric_id,
    metrics.backtest_run_id,
    metrics.backtest_contract_name,
    metrics.backtest_contract_hash,
    runs.model_config_name,
    runs.model_family,
    runs.model_type,
    runs.target,
    runs.grain,
    runs.metric_policy_json,
    runs.primary_metric,
    runs.origin_start,
    runs.origin_end,
    metrics.forecast_origin,
    metrics.horizon,
    metrics.baseline_name,
    metrics.segment_key_json,
    metrics.eligible_count,
    metrics.prediction_count,
    metrics.wape,
    metrics.mae,
    metrics.bias,
    metrics.prediction_completeness,
    metrics.created_at
from {{ source('vertex_ml', 'backtest_metrics') }} as metrics
inner join {{ ref('stg_backtest_runs') }} as runs
    using (backtest_run_id, backtest_contract_name, backtest_contract_hash)
