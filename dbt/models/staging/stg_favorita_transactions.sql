{{ config(
    materialized = "view",
    tags = ["staging"]
) }}

with

favorita_transactions as (
    select
        date,
        store_nbr,
        transactions
    from {{ source('favorita_raw', 'raw_favorita_transactions') }}
),

stores as (
    select store_nbr
    from {{ ref('stg_favorita_stores') }}
)

select
    d.date,
    s.store_nbr,
    t.transactions as store_transactions
from {{ ref('stg_favorita_date_spine') }} as d
cross join stores as s
left join favorita_transactions as t
    on d.date = t.date
    and s.store_nbr = t.store_nbr
