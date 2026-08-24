{{
  config(
    materialized='view',
    tags=['canonical', 'demand', 'series']
  )
}}

-- Favorita adapter for the domain-neutral series contract. Core consumers use the opaque
-- series_key; project dimensions remain available only through entity_key_json and this adapter.
select
    series_key,
    any_value(entity_key_json) as entity_key_json,
    min(period_start) as active_from,
    max(period_start) as active_through,
    true as is_active,
    'favorita_demand' as hierarchy_name,
    'v1' as hierarchy_version
from {{ ref('forecast_eligibility') }}
group by series_key
