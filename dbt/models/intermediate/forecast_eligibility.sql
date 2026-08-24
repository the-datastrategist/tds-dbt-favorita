{{
  config(
    materialized='view',
    tags=['canonical', 'demand', 'eligibility', 'data_quality']
  )
}}

{% set minimum_history_days = var('demand_minimum_history_days', 28) %}
{% set demand_policy = var('demand_policy', 'observed_sales_only') %}

with history as (
    select
        *,
        min(if(observed_sales_units is not null, date, null)) over (
            partition by store_nbr
        ) as first_observed_date,
        countif(observed_sales_units is not null) over (
            partition by store_nbr
            order by date
            rows between unbounded preceding and current row
        ) as observed_history_days
    from {{ ref('int_demand_store_daily') }}
), classified as (
    select
        *,
        observed_history_days >= {{ minimum_history_days }} as has_required_history,
        case
            when not store_open then 'store_closed'
            when not product_active then 'product_inactive'
            when not assortment_active then 'outside_assortment'
            when '{{ demand_policy }}' = 'exclude_stockout_days' and is_stockout then 'stockout'
            when first_observed_date is null then 'no_observed_history'
            when observed_history_days < {{ minimum_history_days }} then 'insufficient_history'
            else null
        end as ineligibility_reason
    from history
)
select
    to_hex(sha256(to_json_string(struct(cast(store_nbr as string) as store_id)))) as series_key,
    to_json_string(struct(cast(store_nbr as string) as store_id)) as entity_key_json,
    date,
    date as period_start,
    store_nbr,
    ineligibility_reason is null as is_eligible,
    ineligibility_reason,
    ineligibility_reason as eligibility_reason,
    unconstrained_demand_units as target_value,
    observed_sales_units is not null as target_observed,
    date as data_cutoff,
    assortment_active,
    store_open,
    product_active,
    has_required_history,
    observed_history_days,
    first_observed_date,
    has_inventory_data,
    is_stockout,
    '{{ demand_policy }}' as demand_policy,
    observed_sales_units,
    unconstrained_demand_units,
    promotion_planned,
    unit_price,
    data_split_source
from classified
