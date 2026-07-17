{{ config(
    materialized='view',
    tags=['vertex', 'staging']
) }}

/*
  Canonical view over Vertex-written SHAP explanation fact table (xgboost, random_forest).
  Joins 1:1 to stg_vertex_model_predictions via prediction_id.
*/
select
    explanation_id,
    prediction_id,
    predict_run_id,
    model_run_id,
    model_id,
    config_name,
    model_family,
    model_type,
    run_at,
    run_date,
    entity_id,
    store_id,
    product_id,
    date,
    predicted_value,
    base_value,
    top_feature_attributions,
    model_artifact_uri
from {{ source('vertex_ml', 'favorita_model_explain') }}
