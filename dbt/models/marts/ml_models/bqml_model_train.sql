{#
  Example BigQuery ML model for sales forecasting
  
  This model creates a BigQuery ML boosted tree regressor model
  using the daily sales features for forecasting.
  
  Usage:
    dbt run --select bqml_sales_forecast
    dbt run-operation evaluate_model --args '{model_name: bqml_sales_forecast}'
#}

{%- set model_configs = var('model_configs', []) -%}
{%- if model_configs | length == 0 -%}
  {{ exceptions.raise_compiler_error("No model_configs found in dbt_project.yml") }}
{%- endif -%}

{%- set option_keys = [
    'model_type',
    'input_label_cols',
    'max_iterations',
    'learn_rate',
    'max_tree_depth',
    'l1_reg',
    'l2_reg',
    'early_stop',
    'booster_type',
    'num_parallel_tree',
    'subsample',
    'colsample_bytree',
    'colsample_bylevel',
    'colsample_bynode',
    'tree_method',
    'min_tree_child_weight',
    'min_split_loss',
    'enable_global_explain',
    'approx_global_feature_contrib',
    'data_split_method',
    'data_split_column',
    'data_split_eval_fraction'
] -%}

{%- set create_statements = [] -%}
{%- for model_config in model_configs -%}
  {%- if 'model_name' not in model_config -%}
    {{ exceptions.raise_compiler_error("Each model_config must include a model_name") }}
  {%- endif -%}
  {%- set include_in_run = model_config.include_in_run if 'include_in_run' in model_config else true -%}
  {%- if include_in_run -%}
    {%- set model_name = model_config.model_name -%}
    {%- set train_ref = model_config.train_ref if 'train_ref' in model_config else 'int_train_input_daily' -%}
    {%- set model_options = [] -%}
  {%- for key in option_keys -%}
    {%- if key in model_config -%}
      {%- set value = model_config[key] -%}
      {%- if key == 'input_label_cols' -%}
        {%- set formatted_value = "['" ~ value | join("', '") ~ "']" -%}
        {%- set _ = model_options.append(key ~ "=" ~ formatted_value) -%}
      {%- elif value == True or value == False -%}
        {%- set formatted_value = value | upper -%}
        {%- set _ = model_options.append(key ~ "=" ~ formatted_value) -%}
      {%- elif value is string -%}
        {%- set formatted_value = "'" ~ value ~ "'" -%}
        {%- set _ = model_options.append(key ~ "=" ~ formatted_value) -%}
      {%- else -%}
        {%- set _ = model_options.append(key ~ "=" ~ value) -%}
      {%- endif -%}
    {%- endif -%}
  {%- endfor -%}

  {%- set feature_columns_list = get_bqml_feature_columns(model_config) -%}
  {%- if 'label_source_column' in model_config -%}
    {%- set label_source = model_config.label_source_column -%}
  {%- elif 'metric' in model_config -%}
    {%- set label_source = model_config.metric ~ '_l1d' -%}
  {%- else -%}
    {%- set label_source = 'sales_company_l1d' -%}
  {%- endif -%}

    {%- set create_statement -%}
CREATE OR REPLACE MODEL `{{ var('project_id') }}.{{ var('dataset') }}.{{ model_name }}`
OPTIONS(
  {{ model_options | join(",\n  ") }}
) AS

SELECT
  {{ feature_columns_list }}
FROM {{ ref(train_ref) }}
WHERE {{ label_source }} IS NOT NULL
  AND date < DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
    {%- endset -%}
    {%- set _ = create_statements.append(create_statement) -%}
  {%- endif -%}
{%- endfor -%}

{%- if create_statements | length == 0 -%}
  {{ exceptions.raise_compiler_error("No models selected for training. Check include_in_run flags.") }}
{%- endif -%}

{{ config(
    materialized='view',
    tags=['bqml', 'train'],
    labels={'model_type': 'bqml'},
    pre_hook="{{ create_statements | join(';\n') }}",
) }}

-- This view is created only to satisfy dbt's materialization requirements
-- The actual BigQuery ML model is created in the pre_hook above
SELECT 1 AS dummy
