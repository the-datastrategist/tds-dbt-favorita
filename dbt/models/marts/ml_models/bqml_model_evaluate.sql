{#
  Evaluate BigQuery ML model performance
  
  Usage:
    dbt run --select bqml_model_evaluation
#}

{%- set model_configs = var('model_configs', []) -%}
{%- if model_configs | length == 0 -%}
  {{ exceptions.raise_compiler_error("No model_configs found in dbt_project.yml") }}
{%- endif -%}

{{ config(
    materialized='incremental',
    unique_key='unique_id',
    partition_by={'field': 'run_date', 'data_type': 'date'},
    incremental_strategy='merge',
    pre_hook="
      {% if is_incremental() %}
        DELETE FROM {{ this }} WHERE run_date = CURRENT_DATE()
      {% endif %}
    ",
    tags=['bqml', 'predict'],
    labels={'model_type': 'bqml', 'purpose': 'evaluation'},
) }}

SELECT
  *
FROM (
  {%- set evaluation_statements = [] -%}
  {%- for model_config in model_configs -%}
    {%- if 'model_name' not in model_config -%}
      {{ exceptions.raise_compiler_error("Each model_config must include a model_name") }}
    {%- endif -%}
    {%- set include_in_run = model_config.include_in_run if 'include_in_run' in model_config else true -%}
    {%- if include_in_run -%}
      {%- set model_name = model_config.model_name -%}
      {%- set train_ref = model_config.train_ref if 'train_ref' in model_config else 'int_train_input_daily' -%}
      {%- set feature_columns_list = get_bqml_feature_columns(model_config) -%}
      {%- if 'label_source_column' in model_config -%}
        {%- set label_source = model_config.label_source_column -%}
      {%- elif 'metric' in model_config -%}
        {%- set label_source = model_config.metric ~ '_l1d' -%}
      {%- else -%}
        {%- set label_source = 'sales_company_l1d' -%}
      {%- endif -%}
      {%- set evaluation_statement -%}
SELECT
  CONCAT('{{ model_name }}', '_', CAST(CURRENT_DATE() AS STRING)) AS unique_id,
  '{{ model_name }}' AS model_name,
  '{{ model_config.version if "version" in model_config else "unknown" }}' AS model_version,
  '{{ model_config.lifecycle if "lifecycle" in model_config else "unknown" }}' AS lifecycle,
  '{{ model_config.metric if "metric" in model_config else "unknown" }}' AS metric,
  '{{ model_config.interval if "interval" in model_config else "unknown" }}' AS `interval`,
  CURRENT_DATE() AS run_date,
  CURRENT_TIMESTAMP() AS evaluation_timestamp,
  *
FROM ML.EVALUATE(
  MODEL `{{ var('project_id') }}.{{ var('dataset') }}.{{ model_name }}`,
  (
    SELECT
      {{ feature_columns_list }}
    FROM {{ ref(train_ref) }}
    WHERE {{ label_source }} IS NOT NULL
      AND date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)  -- Use last 7 days for evaluation
  )
)
      {%- endset -%}
      {%- set _ = evaluation_statements.append(evaluation_statement) -%}
    {%- endif -%}
  {%- endfor -%}
  {%- if evaluation_statements | length == 0 -%}
    {{ exceptions.raise_compiler_error("No models selected for evaluation. Check include_in_run flags.") }}
  {%- endif -%}
  {{ evaluation_statements | join("\nUNION ALL\n") }}
)
{% if is_incremental() %}
  -- Only process if this run_date doesn't exist yet, or replace existing records for today
  WHERE run_date >= CURRENT_DATE()
{% endif %}
