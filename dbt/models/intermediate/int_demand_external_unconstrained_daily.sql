{{ config(materialized='view', tags=['demand', 'optional_source', 'unconstrained_demand']) }}

-- Expected columns: store_id, date, unconstrained_demand_units, source_version.
select
    cast(store_id as int64) as store_nbr,
    cast(date as date) as date,
    cast(unconstrained_demand_units as numeric) as unconstrained_demand_units,
    cast(source_version as string) as unconstrained_demand_source_version
from {{ demand_optional_relation('external_unconstrained_demand') }}
