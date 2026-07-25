{{ config(materialized='view', tags=['vertex', 'staging', 'backtest']) }}

select
    prediction_id,
    backtest_run_id,
    backtest_contract_name,
    backtest_contract_hash,
    forecast_origin,
    target_date,
    horizon,
    entity_key_json,
    segment_key_json,
    baseline_name,
    actual,
    prediction,
    prediction_p10,
    prediction_p50,
    prediction_p90,
    created_at
from {{ source('vertex_ml', 'backtest_predictions') }}
