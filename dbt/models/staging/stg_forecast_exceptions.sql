{{ config(materialized='view', tags=['forecast_operations', 'staging']) }}

select
    exception_id,
    idempotency_key,
    forecast_output_id,
    forecast_run_id,
    exception_type,
    severity,
    exception_status,
    detected_at,
    detected_by,
    details_json,
    resolved_at,
    resolved_by,
    resolution_comment,
    created_at
from {{ source('vertex_ml', 'forecast_exceptions') }}
