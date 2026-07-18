{{ config(materialized='view', tags=['forecast_operations', 'staging']) }}

select
    publication_id,
    idempotency_key,
    forecast_output_id,
    forecast_run_id,
    approval_id,
    publication_version,
    published_value,
    destination,
    delivery_status,
    delivery_reference,
    published_at,
    published_by,
    created_at
from {{ source('vertex_ml', 'forecast_publications') }}
