{#
  WAPE for BigQuery ML predictions, joined back to actuals in the feature table each
  model_config was scored against. ML.EVALUATE doesn't return WAPE natively, so this fills
  the gap for ml_model_leaderboard, using the same metric benchmarks.md already
  recommends as the primary grain-level metric for Vertex models.

  Usage:
    dbt run --select int_bqml_model_wape
#}

{%- set model_configs = var('model_configs', []) -%}

{{ config(
    materialized='view',
    tags=['bqml'],
) }}

with predictions as (
    select * from {{ ref('bqml_model_predict') }}
),

actuals as (
  {%- set actual_statements = [] -%}
  {%- for model_config in model_configs -%}
    {%- if 'model_name' not in model_config -%}
      {{ exceptions.raise_compiler_error("Each model_config must include a model_name") }}
    {%- endif -%}
    {%- set predict_ref = model_config.predict_ref if 'predict_ref' in model_config else 'int_sales_daily' -%}
    {%- set actual_column = model_config.metric if 'metric' in model_config else 'sales_company' -%}
    {%- set actual_statement -%}
select
    '{{ model_config.model_name }}' as model_name,
    date,
    {{ actual_column }} as actual
from {{ ref(predict_ref) }}
    {%- endset -%}
    {%- set _ = actual_statements.append(actual_statement) -%}
  {%- endfor -%}
  {%- if actual_statements | length == 0 -%}
    {{ exceptions.raise_compiler_error("No model_configs found in dbt_project.yml") }}
  {%- endif -%}
  {{ actual_statements | join("\nunion all\n") }}
)

select
    p.model_name,
    p.run_date,
    safe_divide(
        sum(abs(a.actual - p.prediction)),
        sum(abs(a.actual))
    ) as wape
from predictions p
inner join actuals a
    on p.model_name = a.model_name
    and p.date = a.date
where a.actual is not null
group by 1, 2
