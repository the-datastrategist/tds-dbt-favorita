{{ config(
    materialized='view',
    tags=['vertex', 'staging']
) }}

/*
  Canonical view over Vertex-written holdout performance table.
  metric_set is currently always 'test' (see vertex/utils/metadata.py
  performance_row_from_metadata); 'train' metrics live only in
  ml_model_metadata.train_performance (JSON) today.
*/
select
    model_run_id,
    model_id,
    config_name,
    model_family,
    model_type,
    run_at,
    metric_set,
    mean_pred,
    mean_actual,
    mae,
    rmse,
    mse,
    r2,
    mape,
    wape,
    smape,
    bias,
    median_ae
from {{ source('vertex_ml', 'ml_model_performance') }}
