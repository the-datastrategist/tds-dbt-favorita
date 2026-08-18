{{ config(materialized='view', tags=['forecast_delivery', 'monitoring']) }}

with publication_versions as (
    select
        forecast_run_id,
        forecast_contract_name,
        forecast_contract_hash,
        publication_version,
        destination,
        count(*) as publication_row_count,
        min(published_at) as published_at
    from {{ ref('published_forecasts_by_run') }}
    group by 1, 2, 3, 4, 5
), latest_events as (
    select * except (event_rank)
    from (
        select
            events.*,
            row_number() over (
                partition by forecast_run_id, publication_version, destination
                order by occurred_at desc, delivery_event_id desc
            ) as event_rank
        from {{ ref('stg_forecast_delivery_events') }} as events
    )
    where event_rank = 1
)
select
    publications.forecast_run_id,
    publications.forecast_contract_name,
    publications.forecast_contract_hash,
    publications.publication_version,
    publications.destination,
    publications.publication_row_count,
    publications.published_at,
    events.delivery_event_id,
    coalesce(events.delivery_status, 'pending') as delivery_status,
    coalesce(events.delivery_attempt, 1) as delivery_attempt,
    events.delivery_reference,
    events.error_code,
    events.error_message,
    coalesce(events.occurred_at, publications.published_at) as delivery_status_at,
    events.occurred_by,
    case when events.delivery_event_id is null then 'publication_default' else 'delivery_event' end
        as status_source
from publication_versions as publications
left join latest_events as events
    using (forecast_run_id, publication_version, destination)
