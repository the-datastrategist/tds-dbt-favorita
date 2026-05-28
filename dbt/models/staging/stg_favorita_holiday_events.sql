{{ config(
    materialized = "view",
    tags = ["staging"]
    ) 
}}

with

holiday_events as (
    select *
    from {{ source('favorita_raw', 'raw_favorita_holiday_events') }}
)

select
    * except(locale, type),
    locale  as event_locale,
    type    as event_type,

    -- Date Transformations
    extract(day from h.date)        as day_of_month,
    extract(dayofweek from h.date)  as day_of_week,       -- 1 = Sunday, 7 = Saturday
    extract(week from h.date)       as iso_week_of_year,  -- ISO 8601 week
    extract(month from h.date)      as month,
    extract(quarter from h.date)    as quarter,
    extract(year from h.date)       as year,
    -- Week of Month
    ceil(extract(day from h.date) / 7.0) as week_of_month,
    -- ISO week date parts
    extract(isoyear from h.date)    as iso_year,
    extract(isoweek from h.date)    as iso_week,
    -- Additional custom parts
    format_date('%A', h.date)       as day_name,
    format_date('%B', h.date)       as month_name,
from holiday_events h
