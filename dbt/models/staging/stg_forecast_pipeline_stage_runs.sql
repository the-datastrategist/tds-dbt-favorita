{{ config(materialized='view', tags=['forecast_contract', 'publication', 'staging']) }}

select
    stage_run_id,
    forecast_run_id,
    stage_name,
    stage_position,
    component_run_id,
    input_fingerprint,
    output_fingerprint,
    stage_status,
    input_row_count,
    output_row_count,
    started_at,
    finished_at,
    error_message
from {{ source('vertex_ml', 'forecast_pipeline_stage_runs') }}
