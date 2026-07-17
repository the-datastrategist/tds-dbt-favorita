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
    created_at
from {{ source('vertex_ml', 'backtest_predictions') }}
