{{ config(materialized='view', tags=['forecast_operations', 'staging']) }}

select
    approval_id,
    idempotency_key,
    forecast_output_id,
    forecast_run_id,
    override_id,
    decision,
    approved_value,
    reason_code,
    comment,
    decided_at,
    decided_by,
    created_at
from {{ source('vertex_ml', 'forecast_approvals') }}
