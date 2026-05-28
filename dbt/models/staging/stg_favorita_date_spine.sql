{{ config(
    materialized='incremental',
    unique_key='date',
    partition_by={'field': 'date', 'data_type': 'date'},
    incremental_strategy='insert_overwrite',
    tags=['staging']
) }}

with

date_bounds as (
    select
        {% if is_incremental() %}
            date_add((select max(date) from {{ this }}), interval 1 day) as start_date,
        {% else %}
            (select min(date) from {{ source('favorita_raw', 'raw_favorita_train') }}) as start_date,
        {% endif %}
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
where date_bounds.start_date <= date_bounds.end_date
