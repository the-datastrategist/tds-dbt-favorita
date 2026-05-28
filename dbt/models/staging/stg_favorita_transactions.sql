{{ config(
    materialized='incremental',
    unique_key='id',
    partition_by={'field': 'date', 'data_type': 'date'},
    incremental_strategy='insert_overwrite',
    tags=['staging']
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
    {{ dbt_utils.generate_surrogate_key([
        'cast(d.date as string)',
        'cast(s.store_nbr as string)'
    ]) }} as id,
    d.date,
    s.store_nbr,
    t.transactions as store_transactions
from {{ ref('stg_favorita_date_spine') }} as d
cross join stores as s
left join favorita_transactions as t
    on d.date = t.date
    and s.store_nbr = t.store_nbr
where true
{{ filter_incremental_by_date('d.date') }}
