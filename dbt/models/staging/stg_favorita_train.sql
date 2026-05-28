{{ config(
  materialized = "view",
  tags = ["staging"]
  )
}}

with

favorita_train as (
    select *
    from {{ source('favorita_raw', 'raw_favorita_train') }}
),

favorita_items as (
    select
        item_nbr,
        family
    from {{ source('favorita_raw', 'raw_favorita_items') }}
)

select
    {{ dbt_utils.generate_surrogate_key([
        'cast(t.date as string)',
        'cast(t.store_nbr as string)',
        'cast(t.item_nbr as string)'
    ]) }}             as id,
    t.date,
    t.store_nbr,
    t.item_nbr      as product_id,
    i.family        as product_family,
    t.unit_sales    as sales,
    case lower(cast(t.onpromotion as string))
        when 'true' then 1
        else 0
    end             as on_promotion
from favorita_train as t
inner join favorita_items as i
    on t.item_nbr = i.item_nbr
