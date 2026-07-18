{{ config(
    materialized='view',
    tags=['forecast_contract', 'staging']
) }}

select
    forecast_contract_name,
    forecast_contract_hash,
    registered_at,
    target,
    target_unit,
    frequency,
    timezone,
    issue_schedule,
    dimensions,
    horizons,
    quantiles,
    training_window_days,
    known_future_features,
    observed_features,
    hierarchy,
    reconciliation_policy,
    demand_policy,
    contract_json,
    is_active
from {{ source('vertex_ml', 'forecast_contracts') }}
