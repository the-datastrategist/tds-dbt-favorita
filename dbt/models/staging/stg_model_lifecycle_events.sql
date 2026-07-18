{{ config(materialized='view', tags=['vertex', 'staging', 'backtest', 'lifecycle']) }}

select
    lifecycle_event_id,
    candidate_id,
    event_type,
    from_state,
    to_state,
    replaces_candidate_id,
    reason,
    actor,
    occurred_at,
    created_at
from {{ source('vertex_ml', 'model_lifecycle_events') }}
