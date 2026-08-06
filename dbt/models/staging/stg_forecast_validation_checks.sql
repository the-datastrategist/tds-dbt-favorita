{{ config(materialized='view', tags=['forecast_contract', 'publication', 'staging']) }}

select
    validation_check_id,
    forecast_run_id,
    check_name,
    severity,
    passed,
    observed_value,
    threshold_value,
    details_json,
    checked_at
from {{ source('vertex_ml', 'forecast_validation_checks') }}
