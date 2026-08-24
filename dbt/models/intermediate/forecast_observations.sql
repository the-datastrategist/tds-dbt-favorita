{{
  config(
    materialized='view',
    tags=['canonical', 'demand', 'observations']
  )
}}

-- Canonical historical target adapter. Retail columns are intentionally excluded.
select
    to_hex(sha256(to_json_string(struct(cast(store_nbr as string) as store_id)))) as series_key,
    date as period_start,
    unconstrained_demand_units as target_value,
    observed_sales_units is not null as target_observed,
    date as data_cutoff,
    to_json_string(struct(cast(store_nbr as string) as store_id)) as entity_key_json
from {{ ref('int_demand_store_daily') }}
