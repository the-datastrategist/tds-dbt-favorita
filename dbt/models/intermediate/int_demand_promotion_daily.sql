{{ config(materialized='view', tags=['demand', 'optional_source', 'promotion']) }}

-- Expected columns: store_id, date, promotion_planned, promotion_type, plan_version.
select
    cast(store_id as int64) as store_nbr,
    cast(date as date) as date,
    cast(promotion_planned as bool) as promotion_planned,
    cast(promotion_type as string) as promotion_type,
    cast(plan_version as string) as promotion_plan_version
from {{ demand_optional_relation('promotion') }}
