{{ config(
    materialized='incremental',
    unique_key='date',
    partition_by={'field': 'date', 'data_type': 'date'},
    incremental_strategy='insert_overwrite',
    tags=['staging']
) }}

with

favorita_oil as (
    select *
    from {{ source('favorita_raw', 'raw_favorita_oil') }}
)

select
    d.date,
    o.* except (date)
from {{ ref('stg_favorita_date_spine') }} as d
left join favorita_oil as o
    on d.date = o.date
where true
{{ filter_incremental_by_date('d.date') }}
