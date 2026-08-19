{{ config(materialized='view', tags=['monitoring']) }}

{% if var('monitoring_evaluated_at', none) %}
    {% set evaluated_at = "timestamp('" ~ var('monitoring_evaluated_at') ~ "')" %}
{% else %}
    {% set evaluated_at = 'current_timestamp()' %}
{% endif %}

{% set threshold_minutes = var('publication_freshness_threshold_minutes', 1440) %}
{% set monitored_contracts = var('publication_monitored_contracts', []) %}

with contracts as (
    select * except (run_rank)
    from (
        select
            forecast_contract_name,
            forecast_run_id,
            forecast_origin,
            row_number() over (
                partition by forecast_contract_name
                order by started_at desc, forecast_run_id desc
            ) as run_rank
        from {{ ref('stg_forecast_runs') }}
        {% if monitored_contracts %}
        where forecast_contract_name in (
            {% for contract_name in monitored_contracts %}
            '{{ contract_name }}'{% if not loop.last %},{% endif %}
            {% endfor %}
        )
        {% endif %}
    )
    where run_rank = 1
), publications as (
    select
        forecast_contract_name,
        max(published_at) as latest_published_at,
        count(distinct publication_id) as publication_count,
        countif(delivery_status not in ('delivered', 'published')) as unconfirmed_delivery_count
    from {{ ref('published_forecasts_by_run') }}
    group by forecast_contract_name
), source_context as (
    select
        case
            when count(*) > 0 and countif(data_mode = 'continuous') = 0 then 'static_demo'
            else 'continuous'
        end as data_mode
    from {{ ref('stg_source_ingestion_runs') }}
)
select
    contracts.forecast_contract_name,
    contracts.forecast_run_id as latest_forecast_run_id,
    contracts.forecast_origin,
    publications.latest_published_at,
    coalesce(publications.publication_count, 0) as publication_count,
    coalesce(publications.unconfirmed_delivery_count, 0) as unconfirmed_delivery_count,
    {{ evaluated_at }} as evaluated_at,
    source_context.data_mode,
    {{ threshold_minutes }} as threshold_minutes,
    timestamp_diff({{ evaluated_at }}, publications.latest_published_at, minute)
        as publication_age_minutes,
    case
        when source_context.data_mode = 'static_demo' then 'static_demo'
        when publications.latest_published_at is null then 'missing'
        when timestamp_diff({{ evaluated_at }}, publications.latest_published_at, minute)
            > {{ threshold_minutes }} then 'stale'
        else 'fresh'
    end as freshness_status,
    case
        when source_context.data_mode = 'static_demo' then false
        when publications.latest_published_at is null then true
        when timestamp_diff({{ evaluated_at }}, publications.latest_published_at, minute)
            > {{ threshold_minutes }} then true
        else false
    end as is_alerting
from contracts
left join publications using (forecast_contract_name)
cross join source_context
