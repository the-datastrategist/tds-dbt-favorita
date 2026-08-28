{{ config(materialized='view', tags=['demand', 'optional_source', 'closure']) }}

-- Expected columns: store_id, date, is_closed, closure_reason.
select
    cast(store_id as int64) as store_nbr,
    cast(date as date) as date,
    cast(is_closed as bool) as is_closed,
    cast(closure_reason as string) as closure_reason
from {{ demand_optional_relation('closure') }}
