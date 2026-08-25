with observation_keys as (
    select distinct series_key, entity_key_json
    from {{ ref('forecast_observations') }}
), eligibility_keys as (
    select distinct series_key, entity_key_json
    from {{ ref('forecast_eligibility') }}
), series_keys as (
    select series_key, entity_key_json
    from {{ ref('forecast_series') }}
)
select 'observation' as relation_name, observation_keys.*
from observation_keys
left join series_keys using (series_key, entity_key_json)
where series_keys.series_key is null

union all

select 'eligibility' as relation_name, eligibility_keys.*
from eligibility_keys
left join series_keys using (series_key, entity_key_json)
where series_keys.series_key is null
