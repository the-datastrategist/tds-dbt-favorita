{{ config(materialized='view', tags=['monitoring']) }}

{% if var('monitoring_evaluated_at', none) %}
    {% set evaluated_at = "timestamp('" ~ var('monitoring_evaluated_at') ~ "')" %}
{% else %}
    {% set evaluated_at = 'current_timestamp()' %}
{% endif %}

with latest as (
    select * except (run_rank)
    from (
        select
            *,
            row_number() over (
                partition by source_name
                order by finished_at desc, ingestion_run_id desc
            ) as run_rank
        from {{ ref('stg_source_ingestion_runs') }}
    )
    where run_rank = 1
), evaluated as (
    select
        *,
        {{ evaluated_at }} as evaluated_at,
        timestamp_add(
            finished_at,
            interval (expected_interval_hours + allowed_lateness_hours) hour
        ) as freshness_deadline
    from latest
)
select
    *,
    case
        when status != 'succeeded' then 'failed'
        when data_mode = 'static_demo' then 'healthy_static'
        when evaluated_at > freshness_deadline then 'stale'
        else 'healthy'
    end as health_status,
    case
        when status != 'succeeded' then true
        when data_mode = 'continuous' and evaluated_at > freshness_deadline then true
        else false
    end as is_alerting,
    case
        when status != 'succeeded' then concat('latest_ingestion_', status)
        when data_mode = 'static_demo' then 'static_dataset_freshness_not_applicable'
        when evaluated_at > freshness_deadline then 'expected_ingestion_window_missed'
        else 'within_window'
    end as health_reason
from evaluated
