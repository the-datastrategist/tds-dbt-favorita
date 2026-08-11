{{ config(materialized='view', tags=['monitoring']) }}

{% set monitored_metrics = var('drift_monitored_metrics', []) %}
{% set window_days = var('drift_window_days', 28) %}
{% set minimum_observations = var('drift_minimum_observations', 30) %}
{% set maximum_smd = var('drift_maximum_standardized_mean_difference', 0.5) %}

{% for monitored in monitored_metrics %}
{% if not loop.first %}union all{% endif %}
(with scoped as (
    select
        {{ monitored.date_column }} as metric_date,
        safe_cast({{ monitored.metric }} as float64) as metric_value
    from {{ ref(monitored.model) }}
    where {{ monitored.metric }} is not null
    {% if monitored.scope_column is defined %}
        and {{ monitored.scope_column }} = '{{ monitored.scope_value | replace("'", "''") }}'
    {% endif %}
), bounded as (
    select *, max(metric_date) over () as latest_metric_date
    from scoped
), summarized as (
    select
        max(latest_metric_date) as latest_metric_date,
        countif(metric_date > date_sub(latest_metric_date, interval {{ window_days }} day))
            as recent_observation_count,
        countif(
            metric_date > date_sub(latest_metric_date, interval {{ window_days * 2 }} day)
            and metric_date <= date_sub(latest_metric_date, interval {{ window_days }} day)
        ) as reference_observation_count,
        avg(if(metric_date > date_sub(latest_metric_date, interval {{ window_days }} day), metric_value, null))
            as recent_mean,
        avg(if(
            metric_date > date_sub(latest_metric_date, interval {{ window_days * 2 }} day)
            and metric_date <= date_sub(latest_metric_date, interval {{ window_days }} day),
            metric_value,
            null
        )) as reference_mean,
        stddev_pop(if(metric_date > date_sub(latest_metric_date, interval {{ window_days }} day), metric_value, null))
            as recent_stddev,
        stddev_pop(if(
            metric_date > date_sub(latest_metric_date, interval {{ window_days * 2 }} day)
            and metric_date <= date_sub(latest_metric_date, interval {{ window_days }} day),
            metric_value,
            null
        )) as reference_stddev
    from bounded
), measured as (
    select
        *,
        sqrt((pow(recent_stddev, 2) + pow(reference_stddev, 2)) / 2) as pooled_stddev
    from summarized
)
select
    '{{ monitored.model }}' as source_model,
    '{{ monitored.metric }}' as metric_name,
    '{{ monitored.metric_type }}' as metric_type,
    date_sub(latest_metric_date, interval {{ window_days - 1 }} day) as recent_window_start_date,
    latest_metric_date as recent_window_end_date,
    date_sub(latest_metric_date, interval {{ window_days * 2 - 1 }} day) as reference_window_start_date,
    date_sub(latest_metric_date, interval {{ window_days }} day) as reference_window_end_date,
    recent_observation_count,
    reference_observation_count,
    recent_mean,
    reference_mean,
    recent_stddev,
    reference_stddev,
    safe_divide(abs(recent_mean - reference_mean), nullif(pooled_stddev, 0))
        as standardized_mean_difference,
    {{ minimum_observations }} as minimum_observation_count,
    {{ maximum_smd }} as maximum_standardized_mean_difference,
    case
        when recent_observation_count < {{ minimum_observations }}
            or reference_observation_count < {{ minimum_observations }} then 'insufficient_observations'
        when pooled_stddev = 0 and recent_mean != reference_mean then 'drifted'
        when safe_divide(abs(recent_mean - reference_mean), nullif(pooled_stddev, 0)) > {{ maximum_smd }}
            then 'drifted'
        else 'healthy'
    end as drift_status,
    case
        when recent_observation_count < {{ minimum_observations }}
            or reference_observation_count < {{ minimum_observations }} then false
        when pooled_stddev = 0 and recent_mean != reference_mean then true
        when safe_divide(abs(recent_mean - reference_mean), nullif(pooled_stddev, 0)) > {{ maximum_smd }}
            then true
        else false
    end as is_alerting
from measured)
{% else %}
select
    cast(null as string) as source_model,
    cast(null as string) as metric_name,
    cast(null as string) as metric_type,
    cast(null as date) as recent_window_start_date,
    cast(null as date) as recent_window_end_date,
    cast(null as date) as reference_window_start_date,
    cast(null as date) as reference_window_end_date,
    0 as recent_observation_count,
    0 as reference_observation_count,
    cast(null as float64) as recent_mean,
    cast(null as float64) as reference_mean,
    cast(null as float64) as recent_stddev,
    cast(null as float64) as reference_stddev,
    cast(null as float64) as standardized_mean_difference,
    {{ minimum_observations }} as minimum_observation_count,
    {{ maximum_smd }} as maximum_standardized_mean_difference,
    'not_configured' as drift_status,
    true as is_alerting
{% endfor %}
