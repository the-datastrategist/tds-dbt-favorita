{{ config(materialized='view', tags=['forecast_delivery', 'monitoring']) }}

{% if var('monitoring_evaluated_at', none) %}
    {% set evaluated_at = "timestamp('" ~ var('monitoring_evaluated_at') ~ "')" %}
{% else %}
    {% set evaluated_at = 'current_timestamp()' %}
{% endif %}
{% set maximum_pending_minutes = var('delivery_maximum_pending_minutes', 120) %}

with latest_versions as (
    select * except (version_rank)
    from (
        select
            delivery.*,
            row_number() over (
                partition by forecast_contract_name, destination
                order by publication_version desc, published_at desc, forecast_run_id desc
            ) as version_rank
        from {{ ref('forecast_delivery_current') }} as delivery
    )
    where version_rank = 1
)
select
    *,
    {{ evaluated_at }} as evaluated_at,
    timestamp_diff({{ evaluated_at }}, delivery_status_at, minute) as status_age_minutes,
    case
        when delivery_status = 'delivered' then 'healthy'
        when delivery_status = 'pending'
            and timestamp_diff({{ evaluated_at }}, delivery_status_at, minute)
                > {{ maximum_pending_minutes }} then 'overdue'
        else delivery_status
    end as delivery_health_status,
    case
        when delivery_status in ('failed', 'abandoned') then true
        when delivery_status = 'pending'
            and timestamp_diff({{ evaluated_at }}, delivery_status_at, minute)
                > {{ maximum_pending_minutes }} then true
        else false
    end as is_alerting
from latest_versions
