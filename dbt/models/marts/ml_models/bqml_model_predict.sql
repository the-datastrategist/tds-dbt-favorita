{#
  Generate predictions using BigQuery ML model
  
  Usage:
    dbt run --select bqml_predictions
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
    labels={'model_type': 'bqml', 'purpose': 'predictions'},
) }}

SELECT
  *
FROM (
  {%- set prediction_statements = [] -%}
  {%- for model_config in model_configs -%}
    {%- if 'model_name' not in model_config -%}
      {{ exceptions.raise_compiler_error("Each model_config must include a model_name") }}
    {%- endif -%}
    {%- set include_in_forecast = model_config.include_in_forecast if 'include_in_forecast' in model_config else true -%}
    {%- if include_in_forecast -%}
      {%- set model_name = model_config.model_name -%}
      {%- set predict_ref = model_config.predict_ref if 'predict_ref' in model_config else 'int_sales_daily' -%}
      {%- set prediction_features = get_bqml_prediction_features(model_config) -%}
      {%- set label_cols = model_config.input_label_cols if 'input_label_cols' in model_config else [] -%}
      {%- set label_alias = label_cols[0] if label_cols | length > 0 else 'sales_company' -%}
      {%- set predicted_col_name = 'predicted_' ~ label_alias -%}
      {%- set prediction_statement -%}
SELECT
  CONCAT('{{ model_name }}', '_', CAST(CURRENT_DATE() AS STRING), '_', CAST(date AS STRING)) AS unique_id,
  date,
  {{ predicted_col_name }} AS predicted_sales,
  {{ predicted_col_name }} AS prediction,
  CURRENT_DATE()           AS run_date,
  CURRENT_TIMESTAMP()      AS prediction_timestamp,
  '{{ model_name }}'       AS model_name,
  '{{ model_config.version if "version" in model_config else "unknown" }}' AS model_version,
  '{{ model_config.lifecycle if "lifecycle" in model_config else "unknown" }}' AS lifecycle,
  '{{ model_config.metric if "metric" in model_config else "unknown" }}'  AS metric,
  '{{ model_config.interval if "interval" in model_config else "unknown" }}' AS `interval`,
  * EXCEPT(date, feature_as_of_date)
FROM ML.PREDICT(
  MODEL `{{ var('project_id') }}.{{ var('dataset') }}.{{ model_name }}`,
  (
    SELECT
      date,
      feature_as_of_date,
      {{ prediction_features }}
    FROM {{ ref(predict_ref) }}
    WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)  -- Predict for last 14 days
      AND feature_as_of_date = DATE_SUB(date, INTERVAL 1 DAY)
  )
)
      {%- endset -%}
      {%- set _ = prediction_statements.append(prediction_statement) -%}
    {%- endif -%}
  {%- endfor -%}
  {%- if prediction_statements | length == 0 -%}
    {{ exceptions.raise_compiler_error("No models selected for prediction. Check include_in_forecast flags.") }}
  {%- endif -%}
  {{ prediction_statements | join("\nUNION ALL\n") }}
)
{% if is_incremental() %}
  -- Only process if this run_date doesn't exist yet, or replace existing records for today
  WHERE run_date >= CURRENT_DATE()
{% endif %}
