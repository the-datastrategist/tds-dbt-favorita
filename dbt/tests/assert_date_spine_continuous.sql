-- Date spine must have no gaps between min and max date.
{{ config(tags=['data_quality', 'staging']) }}

with spine as (
    select date
    from {{ ref('stg_favorita_date_spine') }}
),

bounds as (
    select
        min(date) as min_date,
        max(date) as max_date
    from spine
),

expected as (
    select date_day as date
    from bounds
    cross join unnest(
        generate_date_array(bounds.min_date, bounds.max_date, interval 1 day)
    ) as date_day
)

select expected.date
from expected
left join spine
    on expected.date = spine.date
where spine.date is null
