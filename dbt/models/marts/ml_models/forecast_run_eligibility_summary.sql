{{ config(materialized='view', tags=['demand', 'eligibility', 'monitoring']) }}

select
    runs.forecast_run_id,
    runs.forecast_contract_name,
    runs.forecast_origin,
    runs.eligibility_snapshot_id,
    summary.demand_policy,
    summary.candidate_entity_count,
    summary.eligible_entity_count,
    summary.excluded_entity_count,
    summary.eligibility_ratio,
    summary.store_closed_count,
    summary.product_inactive_count,
    summary.outside_assortment_count,
    summary.stockout_count,
    summary.no_observed_history_count,
    summary.insufficient_history_count,
    summary.exclusion_sample_json,
    case
        when runs.eligibility_snapshot_id is null then 'missing_snapshot_id'
        when summary.eligibility_date is null then 'missing_eligibility_summary'
        else 'complete'
    end as eligibility_evidence_status
from {{ ref('stg_forecast_runs') }} as runs
left join {{ ref('forecast_eligibility_summary') }} as summary
    on date(runs.forecast_origin) = summary.eligibility_date
