{{ config(materialized='view', tags=['vertex', 'staging', 'backtest', 'lifecycle']) }}

select
    promotion_check_id,
    candidate_id,
    check_name,
    observed_value,
    threshold_value,
    passed,
    details_json,
    created_at
from {{ source('vertex_ml', 'model_promotion_checks') }}
