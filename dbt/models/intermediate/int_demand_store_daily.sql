{{
  config(
    materialized='view',
    tags=['demand', 'features', 'data_quality']
  )
}}

with store_day as (
    select
        date,
        store_nbr,
        max(data_split_source) as data_split_source,
        sum(sales) as observed_sales_units,
        countif(on_promotion = 1) > 0 as promotion_planned
    from {{ ref('stg_favorita_sales_fct') }}
    group by date, store_nbr
)
select
    date,
    store_nbr,
    data_split_source,
    observed_sales_units,
    observed_sales_units as unconstrained_demand_units,
    'observed_sales_only' as demand_policy,
    promotion_planned,
    cast(null as numeric) as unit_price,
    false as has_inventory_data,
    cast(null as numeric) as on_hand_units,
    cast(null as bool) as is_stockout,
    cast(null as bool) as is_demand_censored,
    true as assortment_active,
    true as store_open,
    true as product_active,
    'availability_not_provided' as availability_status
from store_day
