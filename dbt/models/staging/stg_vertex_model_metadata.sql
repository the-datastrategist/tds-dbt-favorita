{{ config(
    materialized='view',
    tags=['vertex', 'staging']
) }}

select
    model_run_id,
    model_id,
    parameter_id,
    config_name,
    model_family,
    model_type,
    run_at,
    target_column,
    gcs_uri,
    joblib_gcs_uri,
    manifest_gcs_uri,
    entity_count,
    entities_fitted,
    train_row_count,
    test_row_count,
    parameters,
    test_performance
from {{ source('vertex_ml', 'favorita_model_metadata') }}
