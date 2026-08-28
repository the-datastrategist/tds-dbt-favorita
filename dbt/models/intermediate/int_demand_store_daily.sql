{{
  config(
    materialized='view',
    tags=['demand', 'features', 'data_quality']
  )
}}

{{ validate_demand_optional_source_policy() }}

with store_day as (
    select
        date,
        store_nbr,
        max(data_split_source) as data_split_source,
        sum(sales) as observed_sales_units,
        countif(on_promotion = 1) > 0 as promotion_planned
    from {{ ref('stg_favorita_sales_fct') }}
    group by date, store_nbr
), enriched as (
    select
        store_day.*,
        inventory.on_hand_units,
        inventory.in_stock,
        inventory.is_stockout as inventory_is_stockout,
        assortment.assortment_active,
        lifecycle.product_active,
        price.unit_price,
        promotion.promotion_planned as optional_promotion_planned,
        closure.is_closed,
        closure.closure_reason,
        external_demand.unconstrained_demand_units as external_unconstrained_demand_units,
        external_demand.unconstrained_demand_source_version
    from store_day
    left join {{ ref('int_demand_inventory_daily') }} as inventory using (store_nbr, date)
    left join {{ ref('int_demand_price_daily') }} as price using (store_nbr, date)
    left join {{ ref('int_demand_promotion_daily') }} as promotion using (store_nbr, date)
    left join {{ ref('int_demand_closure_daily') }} as closure using (store_nbr, date)
    left join {{ ref('int_demand_external_unconstrained_daily') }} as external_demand using (store_nbr, date)
    left join {{ ref('int_demand_assortment') }} as assortment
        on store_day.store_nbr = assortment.store_nbr
       and store_day.date between assortment.start_date and coalesce(assortment.end_date, date '9999-12-31')
    left join {{ ref('int_demand_lifecycle') }} as lifecycle
        on store_day.store_nbr = lifecycle.store_nbr
       and store_day.date between lifecycle.start_date and coalesce(lifecycle.end_date, date '9999-12-31')
)
select
    date,
    store_nbr,
    data_split_source,
    observed_sales_units,
    case
        when '{{ var('demand_policy', 'observed_sales_only') }}' = 'external_unconstrained_demand'
            then external_unconstrained_demand_units
        when '{{ var('demand_policy', 'observed_sales_only') }}' = 'impute_lost_demand_simple'
             and coalesce(inventory_is_stockout, false)
            then observed_sales_units * (1 + {{ var('demand_stockout_uplift_factor', 0.0) }})
        else observed_sales_units
    end as unconstrained_demand_units,
    '{{ var('demand_policy', 'observed_sales_only') }}' as demand_policy,
    coalesce(optional_promotion_planned, promotion_planned) as promotion_planned,
    unit_price,
    inventory_is_stockout is not null or in_stock is not null or on_hand_units is not null as has_inventory_data,
    on_hand_units,
    coalesce(inventory_is_stockout, in_stock = false) as is_stockout,
    coalesce(inventory_is_stockout, in_stock = false) as is_demand_censored,
    coalesce(assortment_active, true) as assortment_active,
    coalesce(is_closed, false) = false as store_open,
    coalesce(product_active, true) as product_active,
    case
        when coalesce(inventory_is_stockout, in_stock = false) then 'confirmed_stockout'
        when inventory_is_stockout is not null or in_stock is not null or on_hand_units is not null then 'inventory_available'
        else 'availability_not_provided'
    end as availability_status,
    closure_reason,
    unconstrained_demand_source_version
from enriched
