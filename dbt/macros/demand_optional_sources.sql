{% macro demand_optional_relation(source_name) %}
  {% set sources = var('demand_optional_sources', {}) %}
  {% set specification = sources.get(source_name, {}) %}
  {% set relation = specification.get('relation') %}
  {% if relation %}
    {{ relation }}
  {% else %}
    (
      select
        cast(null as int64) as store_id,
        cast(null as date) as date,
        cast(null as date) as start_date,
        cast(null as date) as end_date,
        cast(null as numeric) as on_hand_units,
        cast(null as bool) as in_stock,
        cast(null as bool) as is_stockout,
        cast(null as bool) as active,
        cast(null as numeric) as unit_price,
        cast(null as string) as plan_version,
        cast(null as bool) as promotion_planned,
        cast(null as string) as promotion_type,
        cast(null as bool) as is_closed,
        cast(null as string) as closure_reason,
        cast(null as numeric) as unconstrained_demand_units,
        cast(null as string) as source_version
      where false
    )
  {% endif %}
{% endmacro %}

{% macro validate_demand_optional_source_policy() %}
  {% set policy = var('demand_policy', 'observed_sales_only') %}
  {% set allowed_policies = [
    'observed_sales_only',
    'exclude_stockout_days',
    'impute_lost_demand_simple',
    'external_unconstrained_demand'
  ] %}
  {% set required_source_by_policy = {
    'exclude_stockout_days': 'inventory',
    'impute_lost_demand_simple': 'inventory',
    'external_unconstrained_demand': 'external_unconstrained_demand'
  } %}
  {% set sources = var('demand_optional_sources', {}) %}

  {% if policy not in allowed_policies %}
    {% do exceptions.raise_compiler_error(
      "Unsupported demand_policy '" ~ policy ~ "'. Expected one of: " ~ allowed_policies | join(', ')
    ) %}
  {% endif %}

  {% set required_source = required_source_by_policy.get(policy) %}
  {% if required_source and not sources.get(required_source, {}).get('relation') %}
    {% do exceptions.raise_compiler_error(
      "demand_policy '" ~ policy ~ "' requires demand_optional_sources." ~ required_source ~ ".relation"
    ) %}
  {% endif %}

  {% if policy == 'impute_lost_demand_simple' and var('demand_stockout_uplift_factor', 0.0) | float < 0 %}
    {% do exceptions.raise_compiler_error('demand_stockout_uplift_factor must be non-negative') %}
  {% endif %}
{% endmacro %}
