{{ config(
    materialized='view',
    tags=['forecast_contract', 'staging']
) }}

select
    forecast_run_id,
    forecast_contract_name,
    forecast_contract_hash,
    run_type,
    run_status,
    forecast_origin,
    started_at,
    finished_at,
    data_cutoff,
    source_cutoff_json,
    feature_availability_hash,
    feature_materialization_id,
    feature_version,
    code_sha,
    model_run_id,
    model_id,
    config_name,
    row_count,
    error_message
from {{ source('vertex_ml', 'forecast_runs') }}
