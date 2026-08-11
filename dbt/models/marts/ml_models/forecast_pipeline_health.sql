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
), eligibility as (
    select
        forecast_run_id,
        count(*) as persisted_candidate_count,
        countif(is_eligible) as persisted_eligible_count,
        countif(not is_eligible) as persisted_excluded_count,
        countif(has_exception) as persisted_exception_count,
        countif(not is_eligible and nullif(trim(ineligibility_reason), '') is null)
            as unexplained_exclusion_count,
        count(distinct eligibility_snapshot_id) as snapshot_count,
        any_value(eligibility_snapshot_id) as persisted_eligibility_snapshot_id
    from {{ ref('stg_forecast_eligibility_decisions') }}
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
    coalesce(e.persisted_candidate_count, 0) as persisted_candidate_count,
    coalesce(e.persisted_eligible_count, 0) as persisted_eligible_count,
    coalesce(e.persisted_excluded_count, 0) as persisted_excluded_count,
    coalesce(e.persisted_exception_count, 0) as persisted_exception_count,
    coalesce(e.unexplained_exclusion_count, 0) as unexplained_exclusion_count,
    case
        when r.run_status not in ('succeeded', 'draft') then 'failed'
        when coalesce(s.unsuccessful_stage_count, 0) > 0 then 'failed'
        when coalesce(c.failed_blocking_check_count, 0) > 0 then 'gates_failed'
        when coalesce(e.persisted_candidate_count, 0) = 0 then 'missing_eligibility_evidence'
        when e.snapshot_count != 1
            or e.persisted_eligibility_snapshot_id != r.eligibility_snapshot_id
            then 'eligibility_snapshot_mismatch'
        when coalesce(e.unexplained_exclusion_count, 0) > 0 then 'unexplained_exclusions'
        when r.candidate_count != e.persisted_candidate_count
            or r.eligible_count != e.persisted_eligible_count
            or r.excluded_count != e.persisted_excluded_count
            or r.exception_count != e.persisted_exception_count
            or e.persisted_candidate_count != e.persisted_eligible_count + e.persisted_excluded_count
            then 'eligibility_accounting_mismatch'
        when coalesce(o.persisted_output_count, 0) = 0 then 'missing_outputs'
        when o.persisted_output_count != o.distinct_output_count then 'duplicate_outputs'
        when r.row_count != o.persisted_output_count then 'cardinality_mismatch'
        when e.persisted_eligible_count != o.persisted_output_count then 'eligible_prediction_mismatch'
        when coalesce(o.missing_quantile_count, 0) > 0 then 'missing_quantiles'
        else 'healthy'
    end as health_status
from latest_runs r
left join stages s using (forecast_run_id)
left join checks c using (forecast_run_id)
left join outputs o using (forecast_run_id)
left join eligibility e using (forecast_run_id)
