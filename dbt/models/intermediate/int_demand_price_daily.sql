{{ config(materialized='view', tags=['demand', 'optional_source', 'price']) }}

-- Expected columns: store_id, date, unit_price, plan_version.
select
    cast(store_id as int64) as store_nbr,
    cast(date as date) as date,
    cast(unit_price as numeric) as unit_price,
    cast(plan_version as string) as price_plan_version
from {{ demand_optional_relation('price') }}
