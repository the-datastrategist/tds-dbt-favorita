{{ config(
    materialized='incremental',
    unique_key=['store_nbr', 'date'],
    partition_by={'field': 'date', 'data_type': 'date'},
    incremental_strategy='insert_overwrite',
    tags=['staging']
) }}

with

favorita_stores as (
    select
        store_nbr,
        city,
        state
    from {{ ref('stg_favorita_stores') }}
),

favorita_holiday_events as (
    select *
    from {{ ref('stg_favorita_holiday_events') }}
    where true
    {{ filter_incremental_by_date('date') }}
)

select
    s.store_nbr,
    h.date,

    -- Date Transformations
    day_of_month,
    day_of_week,       -- 1 = Sunday, 7 = Saturday
    iso_week_of_year,  -- ISO 8601 week
    month,
    quarter,
    year,
    week_of_month,
    iso_year,
    iso_week,
    day_name,
    month_name,

    -- EVENT BOOLEANS

    -- Specify national events
    max(if(h.event_locale = "National" and h.event_type = "Holiday", true, false))     as is_national_holiday,
    max(if(h.event_locale = "National" and h.event_type = "Event", true, false))       as is_national_event,
    max(if(h.event_locale = "National" and h.event_type = "Additional", true, false))  as is_national_additional,
    max(if(h.event_locale = "National" and h.event_type = "Bridge", true, false))      as is_national_bridge,
    max(if(h.event_locale = "National" and h.event_type = "Work Day", true, false))    as is_national_work_day,
    max(if(h.event_locale = "National" and h.event_type = "Transfer", true, false))    as is_national_transfer,

    -- Specify regional events
    max(if(h.event_locale = "Regional" and h.event_type = "Holiday" and (s.city = h.event_locale or s.state = h.event_locale), true, false))  as is_regional_holiday,

    -- Specify local events
    max(if(h.event_locale = "Local" and h.event_type = "Holiday" and (s.city = h.event_locale or s.state = h.event_locale), true, false))     as is_local_holiday,
    max(if(h.event_locale = "Local" and h.event_type = "Additional" and (s.city = h.event_locale or s.state = h.event_locale), true, false))  as is_local_additional,
    max(if(h.event_locale = "Local" and h.event_type = "Transfer" and (s.city = h.event_locale or s.state = h.event_locale), true, false))    as is_local_transfer

from favorita_stores as s
cross join favorita_holiday_events as h
{{ dbt_utils.group_by(n=13) }}
