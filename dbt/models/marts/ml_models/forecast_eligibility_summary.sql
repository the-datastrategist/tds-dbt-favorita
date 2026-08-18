{{ config(materialized='view', tags=['demand', 'eligibility', 'monitoring']) }}

select
    date as eligibility_date,
    demand_policy,
    count(*) as candidate_entity_count,
    countif(is_eligible) as eligible_entity_count,
    countif(not is_eligible) as excluded_entity_count,
    safe_divide(countif(is_eligible), count(*)) as eligibility_ratio,
    countif(ineligibility_reason = 'store_closed') as store_closed_count,
    countif(ineligibility_reason = 'product_inactive') as product_inactive_count,
    countif(ineligibility_reason = 'outside_assortment') as outside_assortment_count,
    countif(ineligibility_reason = 'stockout') as stockout_count,
    countif(ineligibility_reason = 'no_observed_history') as no_observed_history_count,
    countif(ineligibility_reason = 'insufficient_history') as insufficient_history_count,
    to_json_string(array_agg(
        if(not is_eligible, struct(entity_key_json, ineligibility_reason), null)
        ignore nulls
        order by entity_key_json
        limit 100
    )) as exclusion_sample_json
from {{ ref('forecast_eligibility') }}
group by eligibility_date, demand_policy
