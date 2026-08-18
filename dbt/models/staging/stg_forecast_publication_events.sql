{{ config(materialized='view', tags=['forecast_delivery', 'staging']) }}

select
    publication_event_id,
    idempotency_key,
    event_type,
    forecast_run_id,
    forecast_contract_name,
    forecast_contract_hash,
    publication_version,
    destination,
    row_count,
    occurred_at,
    occurred_by,
    payload_json,
    created_at
from {{ source('vertex_ml', 'forecast_publication_events') }}
