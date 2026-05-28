{% macro filter_incremental_by_date(date_column='date') %}
{%- if is_incremental() -%}
and {{ date_column }} > (
    select coalesce(max(date), date('1900-01-01'))
    from {{ this }}
)
{%- endif -%}
{% endmacro %}
