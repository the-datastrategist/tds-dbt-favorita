{{ config(materialized='view', tags=['vertex', 'staging', 'backtest']) }}

select
    backtest_run_id,
    backtest_contract_name,
    backtest_contract_hash,
    model_config_name,
    target,
    grain,
    metric_policy_json,
    json_value(metric_policy_json, '$.primary_metric') as primary_metric,
    origin_start,
    origin_end,
    prediction_count,
    metric_count,
    status,
    created_at
from {{ source('vertex_ml', 'backtest_runs') }}
where target is not null
    and grain is not null
    and metric_policy_json is not null
