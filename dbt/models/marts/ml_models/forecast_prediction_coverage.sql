{{ config(materialized='view', tags=['monitoring']) }}

{% set minimum_ratio = var('prediction_coverage_minimum_ratio', 0.98) %}

with latest_runs as (
    select * except (run_rank)
    from (
        select
            forecast_run_id,
            forecast_contract_name,
            forecast_origin,
            row_count as expected_output_count,
            row_number() over (
                partition by forecast_contract_name
                order by started_at desc, forecast_run_id desc
            ) as run_rank
        from {{ ref('stg_forecast_runs') }}
    )
    where run_rank = 1
), outputs as (
    select
        forecast_run_id,
        count(*) as predicted_output_count,
        count(distinct forecast_output_id) as distinct_output_count,
        count(distinct horizon) as horizon_count,
        countif(prediction_p50 is null) as missing_point_forecast_count
    from {{ ref('stg_forecast_outputs') }}
    group by forecast_run_id
)
select
    runs.forecast_run_id,
    runs.forecast_contract_name,
    runs.forecast_origin,
    runs.expected_output_count,
    coalesce(outputs.predicted_output_count, 0) as predicted_output_count,
    coalesce(outputs.distinct_output_count, 0) as distinct_output_count,
    coalesce(outputs.horizon_count, 0) as horizon_count,
    coalesce(outputs.missing_point_forecast_count, 0) as missing_point_forecast_count,
    safe_divide(coalesce(outputs.distinct_output_count, 0), runs.expected_output_count)
        as coverage_ratio,
    {{ minimum_ratio }} as minimum_coverage_ratio,
    case
        when runs.expected_output_count is null or runs.expected_output_count <= 0 then 'invalid_scope'
        when coalesce(outputs.missing_point_forecast_count, 0) > 0 then 'missing_predictions'
        when safe_divide(coalesce(outputs.distinct_output_count, 0), runs.expected_output_count)
            < {{ minimum_ratio }} then 'below_threshold'
        else 'healthy'
    end as coverage_status,
    case
        when runs.expected_output_count is null or runs.expected_output_count <= 0 then true
        when coalesce(outputs.missing_point_forecast_count, 0) > 0 then true
        when safe_divide(coalesce(outputs.distinct_output_count, 0), runs.expected_output_count)
            < {{ minimum_ratio }} then true
        else false
    end as is_alerting
from latest_runs as runs
left join outputs using (forecast_run_id)
