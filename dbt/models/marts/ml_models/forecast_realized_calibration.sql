{{ config(materialized='view', tags=['monitoring']) }}

{% set evaluated_at = var('monitoring_evaluated_at', run_started_at) %}
{% set window_days = var('realized_calibration_window_days', 28) %}
{% set minimum_actuals = var('realized_calibration_minimum_actuals', 30) %}
{% set minimum_coverage = var('realized_calibration_minimum_coverage', 0.80) %}
{% set maximum_abs_bias = var('realized_calibration_maximum_absolute_bias_ratio', 0.10) %}

with matured_forecasts as (
    select
        forecast_output_id,
        forecast_run_id,
        forecast_contract_name,
        coalesce(series_key, to_hex(sha256(entity_key_json))) as series_key,
        coalesce(target_timestamp, timestamp(target_date)) as target_timestamp,
        target_date,
        horizon,
        prediction_p10,
        prediction_p50,
        prediction_p90
    from {{ ref('stg_forecast_outputs') }}
    where target_date between date_sub(date({{ dbt.string_literal(evaluated_at) }}), interval {{ window_days - 1 }} day)
        and date({{ dbt.string_literal(evaluated_at) }})
), realized as (
    select
        f.*,
        d.target_value as actual,
        f.prediction_p50 - d.target_value as median_error,
        d.target_value between f.prediction_p10 and f.prediction_p90 as interval_contains_actual
    from matured_forecasts f
    left join {{ ref('forecast_observations') }} d
        on f.series_key = d.series_key
        and date(f.target_timestamp) = d.period_start
), aggregated as (
    select
        forecast_contract_name,
        horizon,
        count(*) as matured_forecast_count,
        count(actual) as realized_actual_count,
        safe_divide(count(actual), count(*)) as realized_actual_ratio,
        safe_divide(countif(interval_contains_actual), count(actual)) as interval_coverage_ratio,
        approx_quantiles(if(actual is not null, median_error, null), 100 ignore nulls)[offset(50)]
            as median_bias,
        safe_divide(
            approx_quantiles(if(actual is not null, median_error, null), 100 ignore nulls)[offset(50)],
            nullif(avg(actual), 0)
        ) as normalized_median_bias,
        avg(if(actual is not null, prediction_p90 - prediction_p10, null)) as mean_interval_width
    from realized
    group by forecast_contract_name, horizon
)
select
    forecast_contract_name,
    horizon,
    date_sub(date({{ dbt.string_literal(evaluated_at) }}), interval {{ window_days - 1 }} day)
        as window_start_date,
    date({{ dbt.string_literal(evaluated_at) }}) as window_end_date,
    matured_forecast_count,
    realized_actual_count,
    realized_actual_ratio,
    interval_coverage_ratio,
    median_bias,
    normalized_median_bias,
    mean_interval_width,
    {{ minimum_actuals }} as minimum_actual_count,
    {{ minimum_coverage }} as minimum_coverage_ratio,
    {{ maximum_abs_bias }} as maximum_absolute_bias_ratio,
    case
        when realized_actual_count < {{ minimum_actuals }} then 'insufficient_actuals'
        when interval_coverage_ratio < {{ minimum_coverage }} then 'under_coverage'
        when normalized_median_bias is null and abs(median_bias) > 0 then 'material_bias'
        when abs(normalized_median_bias) > {{ maximum_abs_bias }} then 'material_bias'
        else 'healthy'
    end as calibration_status,
    case
        when realized_actual_count < {{ minimum_actuals }} then false
        when interval_coverage_ratio < {{ minimum_coverage }} then true
        when normalized_median_bias is null and abs(median_bias) > 0 then true
        when abs(normalized_median_bias) > {{ maximum_abs_bias }} then true
        else false
    end as is_alerting
from aggregated
