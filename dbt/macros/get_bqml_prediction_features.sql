{% macro get_bqml_prediction_features(model_config) %}
  {#-
    Macro to generate the list of feature columns for BigQuery ML model prediction
    
    This macro takes a model config dictionary and returns a formatted list of feature columns
    (without the label column) for the SELECT statement in ML.PREDICT.
    
    Args:
        model_config: Dictionary containing model configuration from dbt_project.yml
        
    Returns:
        String of comma-separated column names formatted for SQL SELECT statement
  -#}
  
  {%- set feature_columns = [] -%}
  {%- if 'feature_columns' in model_config -%}
    {%- set _ = feature_columns.extend(model_config.feature_columns) -%}
  {%- endif -%}
  {%- if 'feature_set_columns' in model_config -%}
    {%- set _ = feature_columns.extend(model_config.feature_set_columns) -%}
  {%- endif -%}
  {%- if 'feature_set_groups' in model_config -%}
    {%- set feature_sets = var('feature_sets', {}) -%}
    {%- for group_name in model_config.feature_set_groups -%}
      {%- if group_name not in feature_sets -%}
        {{ exceptions.raise_compiler_error("feature_set_groups includes undefined group: " ~ group_name) }}
      {%- endif -%}
      {%- set _ = feature_columns.extend(feature_sets[group_name]) -%}
    {%- endfor -%}
  {%- endif -%}
  {%- set deduped_features = [] -%}
  {%- for col in feature_columns -%}
    {%- if col not in deduped_features -%}
      {%- set _ = deduped_features.append(col) -%}
    {%- endif -%}
  {%- endfor -%}
  
  {%- if deduped_features | length == 0 -%}
    {{ exceptions.raise_compiler_error("feature_columns, feature_set_columns, or feature_set_groups must be defined in model config") }}
  {%- endif -%}
  
  {%- set select_columns = [] -%}
  {%- for col in deduped_features -%}
    {%- set _ = select_columns.append(col) -%}
  {%- endfor -%}
  
  {{ return(select_columns | join(",\n      ")) }}
{% endmacro %}
