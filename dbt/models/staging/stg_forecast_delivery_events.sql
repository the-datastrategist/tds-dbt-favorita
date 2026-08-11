{{ config(materialized='view', tags=['forecast_delivery', 'staging', 'monitoring']) }}

select
    delivery_event_id,
    idempotency_key,
    forecast_run_id,
    publication_version,
    destination,
    delivery_status,
    delivery_attempt,
    delivery_reference,
    error_code,
    error_message,
    occurred_at,
    occurred_by,
    details_json,
    created_at
from {{ source('vertex_ml', 'forecast_delivery_events') }}
