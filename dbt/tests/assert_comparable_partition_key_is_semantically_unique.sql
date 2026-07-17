-- Regression guard: company-day and store-day rows can never share a champion partition.
{{ config(tags=['data_quality', 'ml_models', 'backtest']) }}

select comparable_partition_key
from {{ ref('favorita_model_leaderboard') }}
group by comparable_partition_key
having count(distinct to_json_string(struct(
    target, grain, horizon, segment_key_json, metric_policy
))) > 1
