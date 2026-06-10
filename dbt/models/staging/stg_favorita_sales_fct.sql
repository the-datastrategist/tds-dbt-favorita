{{ config(
    materialized='table',
    partition_by={'field': 'date', 'data_type': 'date'},
    tags=['staging']
) }}

with

train as (
    select
        id,
        date,
        store_nbr,
        product_id,
        product_family,
        sales,
        on_promotion,
        'train' as data_split_source
    from {{ ref('stg_favorita_train') }}
),

test as (
    select
        id,
        date,
        store_nbr,
        product_id,
        product_family,
        cast(null as float64) as sales,
        on_promotion,
        'test' as data_split_source
    from {{ ref('stg_favorita_test') }}
),

favorita_sales_fct as (
    select * from train
    union all
    select * from test
)

select * from favorita_sales_fct
