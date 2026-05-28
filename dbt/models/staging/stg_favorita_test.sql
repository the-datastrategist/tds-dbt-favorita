{{ config(
  materialized = "view",
  tags = ["staging"]
  ) 
}}

with

favorita_test as (
    select *
    from {{ source('favorita_raw', 'raw_favorita_test') }}
)

select  
  date,
  store_nbr,
  id          as product_id,
  family      as product_family,
  onpromotion as on_promotion
from favorita_test
