{{ config(materialized='view', tags=['forecast_operations', 'fva']) }}

with published as (
    select
        publications.forecast_run_id,
        outputs.forecast_contract_name,
        outputs.forecast_contract_hash,
        publications.publication_version,
        publications.destination,
        outputs.grain,
        outputs.horizon,
        approvals.decided_by as planner,
        coalesce(overrides.reason_code, 'no_override') as reason_code,
        outputs.target_date,
        safe_cast(json_value(outputs.entity_key_json, '$.store_nbr') as int64) as store_nbr,
        outputs.prediction_p50 as statistical_forecast,
        coalesce(overrides.override_value, outputs.prediction_p50) as planner_adjusted_forecast,
        publications.published_value as published_forecast
    from {{ ref('stg_forecast_publications') }} as publications
    inner join {{ ref('stg_forecast_outputs') }} as outputs
        using (forecast_output_id, forecast_run_id)
    inner join {{ ref('stg_forecast_approvals') }} as approvals
        using (approval_id, forecast_output_id, forecast_run_id)
    left join {{ ref('stg_forecast_overrides') }} as overrides
        using (override_id, forecast_output_id, forecast_run_id)
), scored as (
    select
        published.*,
        actuals.unconstrained_demand_units as actual,
        actuals.unconstrained_demand_units is not null as has_actual
    from published
    left join {{ ref('int_demand_store_daily') }} as actuals
        on published.target_date = actuals.date
        and published.store_nbr = actuals.store_nbr
), aggregate_errors as (
    select
        forecast_run_id,
        forecast_contract_name,
        forecast_contract_hash,
        publication_version,
        destination,
        grain,
        horizon,
        planner,
        reason_code,
        count(*) as forecast_count,
        countif(has_actual) as actual_count,
        safe_divide(
            sum(if(has_actual, abs(actual - statistical_forecast), 0)),
            sum(if(has_actual, abs(actual), 0))
        ) as statistical_wape,
        safe_divide(
            sum(if(has_actual, abs(actual - planner_adjusted_forecast), 0)),
            sum(if(has_actual, abs(actual), 0))
        ) as planner_adjusted_wape,
        safe_divide(
            sum(if(has_actual, abs(actual - published_forecast), 0)),
            sum(if(has_actual, abs(actual), 0))
        ) as published_wape
    from scored
    group by 1, 2, 3, 4, 5, 6, 7, 8, 9
)
select
    *,
    safe_divide(actual_count, forecast_count) as actual_coverage,
    case
        when actual_count = 0 then 'awaiting_actuals'
        when actual_count != forecast_count then 'incomplete_actuals'
        when statistical_wape is null or planner_adjusted_wape is null or published_wape is null
            then 'undefined_metric'
        else 'comparable'
    end as comparison_status,
    if(actual_count = forecast_count, statistical_wape - planner_adjusted_wape, null)
        as planner_wape_fva_points,
    if(actual_count = forecast_count, planner_adjusted_wape - published_wape, null)
        as publication_wape_fva_points,
    if(actual_count = forecast_count, statistical_wape - published_wape, null)
        as total_wape_fva_points
from aggregate_errors
