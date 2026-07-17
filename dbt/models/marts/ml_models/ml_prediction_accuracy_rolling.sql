{#
  Rolling 7-day and 28-day trailing accuracy per config_name, alongside the model_run_id's
  training-time (test) performance for comparison. Powers assert_no_material_accuracy_drift.
#}

{{ config(
    materialized='table',
    tags=['vertex'],
) }}

select
    a.config_name,
    a.model_family,
    a.model_type,
    a.model_run_id,
    a.forecast_date,
    a.n_predictions,
    a.mae,
    a.wape,
    a.bias,
    avg(a.mae) over (
        partition by a.config_name order by a.forecast_date
        rows between 6 preceding and current row
    ) as mae_7d,
    avg(a.wape) over (
        partition by a.config_name order by a.forecast_date
        rows between 6 preceding and current row
    ) as wape_7d,
    avg(a.mae) over (
        partition by a.config_name order by a.forecast_date
        rows between 27 preceding and current row
    ) as mae_28d,
    avg(a.wape) over (
        partition by a.config_name order by a.forecast_date
        rows between 27 preceding and current row
    ) as wape_28d,
    p.mae as train_test_mae,
    p.wape as train_test_wape
from {{ ref('int_vertex_prediction_accuracy_daily') }} a
left join {{ ref('stg_vertex_model_performance') }} p
    on a.model_run_id = p.model_run_id
    and p.metric_set = 'test'
