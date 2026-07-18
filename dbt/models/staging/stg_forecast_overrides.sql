{{ config(materialized='view', tags=['forecast_operations', 'staging']) }}

select
    override_id,
    idempotency_key,
    forecast_output_id,
    forecast_run_id,
    override_value,
    reason_code,
    comment,
    overridden_at,
    overridden_by,
    created_at
from {{ source('vertex_ml', 'forecast_overrides') }}
