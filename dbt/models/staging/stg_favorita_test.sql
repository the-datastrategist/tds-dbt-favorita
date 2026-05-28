{{ config(
  materialized = "view",
  tags = ["staging"]
  ) 
}}

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
)

select
    t.date,
    t.store_nbr,
    t.item_nbr      as product_id,
    i.family        as product_family,
    case lower(cast(t.onpromotion as string))
        when 'true' then 1
        else 0
    end             as on_promotion
from favorita_test as t
left join favorita_items as i
    on t.item_nbr = i.item_nbr
