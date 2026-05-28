{{ config(
    materialized = "view",
    tags = ["staging"]
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
