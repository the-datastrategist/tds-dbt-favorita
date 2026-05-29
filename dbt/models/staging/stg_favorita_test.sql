{{ config(
    materialized='incremental',
    unique_key='id',
    partition_by={'field': 'date', 'data_type': 'date'},
    incremental_strategy='insert_overwrite',
    tags=['staging']
) }}

with

favorita_test as (
    select *
    from {{ source('favorita_raw', 'raw_favorita_test') }}
),

favorita_items as (
    select
        item_nbr,
        family
    from {{ source('favorita_raw', 'raw_favorita_items') }}
),

test_store_products as (
    select distinct
        store_nbr,
        item_nbr
    from favorita_test
),

test_dates as (
    select d.date
    from {{ ref('stg_favorita_date_spine') }} as d
    inner join (
        select
            min(date) as start_date,
            max(date) as end_date
        from favorita_test
    ) as bounds
        on d.date between bounds.start_date and bounds.end_date
    where true
    {{ filter_incremental_by_date('d.date') }}
)

select
    {{ dbt_utils.generate_surrogate_key([
        'cast(td.date as string)',
        'cast(tsp.store_nbr as string)',
        'cast(tsp.item_nbr as string)'
    ]) }} as id,
    td.date,
    tsp.store_nbr,
    tsp.item_nbr as product_id,
    i.family as product_family,
    case lower(cast(t.onpromotion as string))
        when 'true' then 1
        else 0
    end as on_promotion
from test_dates as td
cross join test_store_products as tsp
left join favorita_test as t
    on td.date = t.date
    and tsp.store_nbr = t.store_nbr
    and tsp.item_nbr = t.item_nbr
left join favorita_items as i
    on tsp.item_nbr = i.item_nbr
