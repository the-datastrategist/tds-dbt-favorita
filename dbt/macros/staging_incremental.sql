{% macro staging_date_partition_config(unique_key=none) %}
{%- set config_dict = {
    'materialized': 'incremental',
    'partition_by': {'field': 'date', 'data_type': 'date'},
    'incremental_strategy': 'insert_overwrite',
    'tags': ['staging'],
} -%}
{%- if unique_key is not none -%}
  {%- do config_dict.update({'unique_key': unique_key}) -%}
{%- endif -%}
{{ return(config_dict) }}
{% endmacro %}


{% macro staging_dimension_config(unique_key) %}
{{ return({
    'materialized': 'incremental',
    'unique_key': unique_key,
    'incremental_strategy': 'merge',
    'tags': ['staging'],
}) }}
{% endmacro %}


{% macro filter_incremental_by_date(date_column='date') %}
{%- if is_incremental() -%}
and {{ date_column }} > (
    select coalesce(max({{ date_column }}), date('1900-01-01'))
    from {{ this }}
)
{%- endif -%}
{% endmacro %}
