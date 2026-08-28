{{ config(materialized='view', tags=['demand', 'optional_source', 'inventory']) }}

-- Opt in with vars.demand_optional_sources.inventory.relation. The external relation must expose
-- store_id, date, on_hand_units, in_stock, and is_stockout using the documented interface.
select
    cast(store_id as int64) as store_nbr,
    cast(date as date) as date,
    cast(on_hand_units as numeric) as on_hand_units,
    cast(in_stock as bool) as in_stock,
    cast(is_stockout as bool) as is_stockout
from {{ demand_optional_relation('inventory') }}
