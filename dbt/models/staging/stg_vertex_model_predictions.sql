{{ config(
    materialized='view',
    tags=['vertex', 'staging']
) }}

/*
  Canonical view over Vertex-written prediction fact table.
  Downstream marts can filter by model_type, model_family, or latest predict_run_id.
*/
select
    prediction_id,
    predict_run_id,
    model_run_id,
    model_id,
    config_name,
    model_family,
    model_type,
    run_at,
    run_date,
    target_column,
    entity_id,
    store_id,
    product_id,
    date,
    forecast_date,
    forecast_horizon,
    actual,
    prediction,
    prediction_lower,
    prediction_upper,
    model_artifact_uri
from {{ source('vertex_ml', 'favorita_model_predictions') }}
