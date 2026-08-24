{{
  config(
    materialized='view',
    tags=['canonical', 'features', 'train', 'store_adapter']
  )
}}

-- Favorita store-grain adapter for the domain-neutral runtime contract. Legacy feature columns
-- remain payload fields during migration, while core consumers use the canonical identity,
-- temporal, target, eligibility, and cutoff roles below.
select
    to_hex(sha256(to_json_string(struct(cast(store_nbr as string) as store_id)))) as series_key,
    to_json_string(struct(cast(store_nbr as string) as store_id)) as entity_key_json,
    date as period_start,
    sales_store as target_value,
    sales_store is not null as target_observed,
    true as is_eligible,
    cast(null as string) as eligibility_reason,
    date as data_cutoff,
    sales_store_n7d as target_horizon_7,
    *
from {{ ref('int_sales_store_daily') }}
