{{ config(
    materialized = "view",
    tags = ["staging"]
) }}

with

date_bounds as (
    select
        (select min(date) from {{ source('favorita_raw', 'raw_favorita_train') }}) as start_date,
        (select max(date) from {{ source('favorita_raw', 'raw_favorita_test') }}) as end_date
)

select date_day as date
from date_bounds
cross join unnest(
    generate_date_array(
        date_bounds.start_date,
        date_bounds.end_date,
        interval 1 day
    )
) as date_day
