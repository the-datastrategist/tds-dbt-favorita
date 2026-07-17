{#
  Snapshot of the current champion config per grain: the best-performing config (by
  leaderboard_primary_metric_by_grain) among each config's own latest run.

  Materialized as a table, so only the current champion is visible here — see
  docs/specs/model_leaderboard_mart.md "Open questions" for the case for promoting this to a
  dbt snapshot if "when did the champion change" becomes a client deliverable.
#}

{%- set primary_metric_by_grain = var('leaderboard_primary_metric_by_grain', {'store-day': 'wape', 'company-day': 'mae'}) -%}

{{ config(
    materialized='table',
    tags=['bqml', 'vertex'],
) }}

with latest_run_per_config as (
    select
        *,
        row_number() over (
            partition by config_name
            order by run_at desc
        ) = 1 as is_latest_run
    from {{ ref('ml_model_leaderboard') }}
),

champion as (
    select
        *,
        row_number() over (
            partition by grain
            order by
                case grain
                {%- for grain, metric in primary_metric_by_grain.items() %}
                    when '{{ grain }}' then {{ metric }}
                {%- endfor %}
                    else mae
                end asc
        ) = 1 as is_champion
    from latest_run_per_config
    where is_latest_run
)

select
    platform,
    config_name,
    model_run_id,
    model_family,
    model_type,
    grain,
    run_at,
    mae,
    rmse,
    r2,
    wape,
    is_champion
from champion
