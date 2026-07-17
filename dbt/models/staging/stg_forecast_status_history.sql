{{ config(
    materialized='view',
    tags=['forecast_contract', 'staging']
) }}

select
    status_event_id,
    forecast_output_id,
    forecast_run_id,
    previous_status,
    new_status,
    changed_at,
    changed_by,
    reason_code,
    comment
from {{ source('vertex_ml', 'forecast_status_history') }}
