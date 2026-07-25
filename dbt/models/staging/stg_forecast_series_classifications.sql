{{ config(materialized='view', tags=['vertex', 'staging', 'forecast']) }}

select
    classification_id,
    classification_run_id,
    forecast_contract_name,
    forecast_contract_hash,
    forecast_origin,
    entity_key_json,
    history_length,
    nonzero_observation_count,
    average_demand_interval,
    coefficient_of_variation_squared,
    is_intermittent,
    is_cold_start,
    recommended_strategy,
    routing_policy_hash,
    classified_at
from {{ source('vertex_ml', 'forecast_series_classifications') }}
