{{ config(materialized='view', tags=['vertex', 'backtest', 'lifecycle']) }}

select *
from {{ ref('ml_model_lifecycle_current') }}
where lifecycle_state = 'champion'
qualify row_number() over (
    partition by model_scope_key
    order by latest_event_at desc, latest_lifecycle_event_id desc
) = 1
