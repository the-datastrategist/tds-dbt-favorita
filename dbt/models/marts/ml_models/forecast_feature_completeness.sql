{{ config(materialized='view', tags=['monitoring']) }}

{% set monitored_models = var('feature_completeness_monitored_models', []) %}
{% set minimum_ratio = var('feature_completeness_minimum_ratio', 0.99) %}
{% set minimum_entity_ratio = var('feature_completeness_minimum_entity_ratio', 0.95) %}

{% for monitored in monitored_models %}
{% if not loop.first %}union all{% endif %}
with dated as (
    select
        {{ monitored.date_column }} as feature_date,
        {{ monitored.entity_column }} as entity_key,
        {% for column in monitored.required_columns %}
        {{ column }}{% if not loop.last %},{% endif %}
        {% endfor %}
    from {{ ref(monitored.model) }}
    {% if monitored.scope_column is defined %}
    where {{ monitored.scope_column }} = '{{ monitored.scope_value | replace("'", "''") }}'
    {% endif %}
), ranked_dates as (
    select
        feature_date,
        dense_rank() over (order by feature_date desc) as date_rank
    from (select distinct feature_date from dated where feature_date is not null)
), scoped as (
    select dated.*, ranked_dates.date_rank
    from dated
    join ranked_dates using (feature_date)
    where ranked_dates.date_rank <= 2
), summarized as (
    select
        date_rank,
        max(feature_date) as feature_date,
        count(*) as row_count,
        count(distinct entity_key) as entity_count,
        {% for column in monitored.required_columns %}
        countif({{ column }} is null){% if not loop.last %} +{% endif %}
        {% endfor %} as missing_required_value_count
    from scoped
    group by date_rank
), latest as (
    select * from summarized where date_rank = 1
), previous as (
    select * from summarized where date_rank = 2
)
select
    '{{ monitored.model }}' as feature_model,
    latest.feature_date,
    latest.row_count,
    latest.entity_count,
    coalesce(previous.entity_count, latest.entity_count) as previous_entity_count,
    latest.missing_required_value_count,
    {{ monitored.required_columns | length }} as required_feature_count,
    safe_divide(
        latest.row_count * {{ monitored.required_columns | length }}
            - latest.missing_required_value_count,
        latest.row_count * {{ monitored.required_columns | length }}
    ) as completeness_ratio,
    safe_divide(latest.entity_count, coalesce(previous.entity_count, latest.entity_count))
        as entity_coverage_ratio,
    {{ minimum_ratio }} as minimum_completeness_ratio,
    {{ minimum_entity_ratio }} as minimum_entity_coverage_ratio,
    case
        when latest.row_count = 0 then 'missing_rows'
        when safe_divide(
            latest.row_count * {{ monitored.required_columns | length }}
                - latest.missing_required_value_count,
            latest.row_count * {{ monitored.required_columns | length }}
        ) < {{ minimum_ratio }} then 'missing_required_values'
        when safe_divide(latest.entity_count, coalesce(previous.entity_count, latest.entity_count))
            < {{ minimum_entity_ratio }} then 'entity_coverage_low'
        else 'healthy'
    end as feature_completeness_status,
    case
        when latest.row_count = 0 then true
        when safe_divide(
            latest.row_count * {{ monitored.required_columns | length }}
                - latest.missing_required_value_count,
            latest.row_count * {{ monitored.required_columns | length }}
        ) < {{ minimum_ratio }} then true
        when safe_divide(latest.entity_count, coalesce(previous.entity_count, latest.entity_count))
            < {{ minimum_entity_ratio }} then true
        else false
    end as is_alerting
from latest
left join previous on true
{% else %}
select
    cast(null as string) as feature_model,
    cast(null as date) as feature_date,
    0 as row_count,
    0 as entity_count,
    0 as previous_entity_count,
    0 as missing_required_value_count,
    0 as required_feature_count,
    cast(null as float64) as completeness_ratio,
    cast(null as float64) as entity_coverage_ratio,
    {{ minimum_ratio }} as minimum_completeness_ratio,
    {{ minimum_entity_ratio }} as minimum_entity_coverage_ratio,
    'not_configured' as feature_completeness_status,
    true as is_alerting
{% endfor %}
