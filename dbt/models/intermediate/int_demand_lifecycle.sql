{{ config(materialized='view', tags=['demand', 'optional_source', 'lifecycle']) }}

-- Entity-level lifecycle adapter. Expected columns: store_id, start_date, end_date, active.
select
    cast(store_id as int64) as store_nbr,
    cast(start_date as date) as start_date,
    cast(end_date as date) as end_date,
    cast(active as bool) as product_active
from {{ demand_optional_relation('lifecycle') }}
