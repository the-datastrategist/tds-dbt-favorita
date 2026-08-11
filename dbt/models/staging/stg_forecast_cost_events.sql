{{ config(materialized='view', tags=['monitoring', 'staging']) }}

select
    cost_event_id,
    service_name,
    cost_type,
    usage_start_at,
    usage_end_at,
    amount_usd,
    currency,
    forecast_contract_name,
    forecast_run_id,
    model_run_id,
    stage_name,
    environment,
    usage_amount,
    usage_unit,
    bytes_processed,
    slot_ms,
    source_system,
    source_event_id,
    labels_json,
    recorded_at
from {{ source('vertex_ml', 'forecast_cost_events') }}
