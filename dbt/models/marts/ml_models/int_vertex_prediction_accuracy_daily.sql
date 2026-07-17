{#
  One row per (config_name, forecast_date), aggregating stg_vertex_model_predictions rows
  where actual is now known. forecast_date (not run_date) is the grouping key: a prediction
  made on day T for T+7 only becomes checkable on T+7 once actual lands, so this table fills
  in retroactively as actuals arrive. Feeds favorita_prediction_accuracy_rolling.

  Note: unique_key + BigQuery's default merge incremental_strategy make this idempotent, but
  every run still scans all of stg_vertex_model_predictions rather than filtering by an
  incremental date window — acceptable at this data volume, revisit if it becomes slow.
#}

{{ config(
    materialized='incremental',
    unique_key=['config_name', 'forecast_date'],
    partition_by={'field': 'forecast_date', 'data_type': 'date'},
    tags=['vertex'],
) }}

select
    config_name,
    model_family,
    model_type,
    model_run_id,
    forecast_date,
    count(*) as n_predictions,
    avg(abs(actual - prediction)) as mae,
    safe_divide(sum(abs(actual - prediction)), sum(abs(actual))) as wape,
    avg(prediction - actual) as bias
from {{ ref('stg_vertex_model_predictions') }}
where actual is not null
    and forecast_date is not null
group by config_name, model_family, model_type, model_run_id, forecast_date
