{{ config(
  materialized = "view",
  tags = ["staging"]
  )
}}

with

favorita_train as (
    select *
    from {{ source('favorita_raw', 'raw_favorita_train') }}
)

select  
  date,
  store_nbr,
  id          as product_id,
  family      as product_family,
  sales,
  onpromotion as on_promotion
from favorita_train
