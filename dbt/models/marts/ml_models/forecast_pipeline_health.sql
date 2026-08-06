{{ config(materialized='view', tags=['monitoring']) }}

with latest_runs as (
    select * except (run_rank)
    from (
        select
            *,
            row_number() over (
                partition by forecast_contract_name
                order by started_at desc, forecast_run_id desc
            ) as run_rank
        from {{ ref('stg_forecast_runs') }}
    )
    where run_rank = 1
), stages as (
    select
        forecast_run_id,
        count(*) as stage_count,
        countif(stage_status != 'completed') as unsuccessful_stage_count,
        max(stage_position) as maximum_stage_position
    from {{ ref('stg_forecast_pipeline_stage_runs') }}
    group by forecast_run_id
), checks as (
    select
        forecast_run_id,
        countif(severity = 'blocking') as blocking_check_count,
        countif(severity = 'blocking' and not passed) as failed_blocking_check_count
    from {{ ref('stg_forecast_validation_checks') }}
    group by forecast_run_id
), outputs as (
    select
        forecast_run_id,
        count(*) as persisted_output_count,
        count(distinct forecast_output_id) as distinct_output_count,
        count(distinct horizon) as horizon_count,
        countif(prediction_p10 is null or prediction_p50 is null or prediction_p90 is null)
            as missing_quantile_count
    from {{ ref('stg_forecast_outputs') }}
    group by forecast_run_id
)
select
    r.*,
    coalesce(s.stage_count, 0) as stage_count,
    coalesce(s.unsuccessful_stage_count, 0) as unsuccessful_stage_count,
    coalesce(s.maximum_stage_position, 0) as maximum_stage_position,
    coalesce(c.blocking_check_count, 0) as blocking_check_count,
    coalesce(c.failed_blocking_check_count, 0) as failed_blocking_check_count,
    coalesce(o.persisted_output_count, 0) as persisted_output_count,
    coalesce(o.distinct_output_count, 0) as distinct_output_count,
    coalesce(o.horizon_count, 0) as horizon_count,
    coalesce(o.missing_quantile_count, 0) as missing_quantile_count,
    case
        when r.run_status not in ('succeeded', 'draft') then 'failed'
        when coalesce(s.unsuccessful_stage_count, 0) > 0 then 'failed'
        when coalesce(c.failed_blocking_check_count, 0) > 0 then 'gates_failed'
        when coalesce(o.persisted_output_count, 0) = 0 then 'missing_outputs'
        when o.persisted_output_count != o.distinct_output_count then 'duplicate_outputs'
        when r.row_count != o.persisted_output_count then 'cardinality_mismatch'
        when coalesce(o.missing_quantile_count, 0) > 0 then 'missing_quantiles'
        else 'healthy'
    end as health_status
from latest_runs r
left join stages s using (forecast_run_id)
left join checks c using (forecast_run_id)
left join outputs o using (forecast_run_id)
