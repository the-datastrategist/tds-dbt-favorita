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
    sales.date as period_start,
    sales.store_nbr,
    eligibility.target_value,
    eligibility.target_observed,
    eligibility.is_eligible,
    eligibility.eligibility_reason,
    eligibility.data_cutoff,
    eligibility.demand_policy,
    eligibility.has_inventory_data,
    eligibility.is_stockout,
    eligibility.assortment_active,
    eligibility.store_open,
    eligibility.product_active,
    eligibility.unit_price,
    eligibility.promotion_planned,
    sales_store_n7d as target_horizon_7,
    sales.* except (date, store_nbr)
from {{ ref('int_sales_store_daily') }} as sales
left join {{ ref('forecast_eligibility') }} as eligibility
    on sales.store_nbr = eligibility.store_nbr
   and sales.date = eligibility.date
