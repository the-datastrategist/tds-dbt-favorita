{#
  Generate SHAP (SHapley Additive exPlanations) values for BigQuery ML model predictions
  
  This model uses ML.EXPLAIN_PREDICT to calculate feature attributions (SHAP values)
  for each prediction, showing how each feature contributes to the models output.
  
  Usage:
    dbt run --select bqml_model_explain
#}

{%- set model_configs = var('model_configs', []) -%}
{%- set top_k_features = var('bqml_explain_top_k_features', 20) -%}
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
    labels={'model_type': 'bqml', 'purpose': 'explain'},
) }}

SELECT
  *
FROM (
  {%- set explain_statements = [] -%}
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
      {%- set explain_statement -%}
SELECT
  CONCAT('{{ model_name }}', '_', CAST(CURRENT_DATE() AS STRING), '_', CAST(date AS STRING)) AS unique_id,
  date,
  CURRENT_DATE() AS run_date,
  '{{ model_name }}' AS model_name,
  '{{ model_config.version if "version" in model_config else "unknown" }}' AS model_version,
  '{{ model_config.lifecycle if "lifecycle" in model_config else "unknown" }}' AS lifecycle,
  '{{ model_config.metric if "metric" in model_config else "unknown" }}' AS metric,
  '{{ model_config.interval if "interval" in model_config else "unknown" }}' AS `interval`,
  CURRENT_TIMESTAMP() AS explain_timestamp,
  explain.predicted_{{ label_alias }} AS predicted_value,
  explain.top_feature_attributions
FROM ML.EXPLAIN_PREDICT(
  MODEL `{{ var('project_id') }}.{{ var('dataset') }}.{{ model_name }}`,
  (
    SELECT
      date,
      feature_as_of_date,
      {{ prediction_features }}
    FROM {{ ref(predict_ref) }}
    WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)  -- Explain predictions for last 14 days
      AND feature_as_of_date = DATE_SUB(date, INTERVAL 1 DAY)
  ),
  STRUCT({{ top_k_features }} AS top_k_features)  -- Return top N most important features per prediction
) AS explain
      {%- endset -%}
      {%- set _ = explain_statements.append(explain_statement) -%}
    {%- endif -%}
  {%- endfor -%}
  {%- if explain_statements | length == 0 -%}
    {{ exceptions.raise_compiler_error("No models selected for explain. Check include_in_forecast flags.") }}
  {%- endif -%}
  {{ explain_statements | join("\nUNION ALL\n") }}
)
{% if is_incremental() %}
  -- Only process if this run_date doesn't exist yet, or replace existing records for today
  WHERE run_date >= CURRENT_DATE()
{% endif %}
