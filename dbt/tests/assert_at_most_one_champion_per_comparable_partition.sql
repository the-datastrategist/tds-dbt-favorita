-- No target/grain/horizon/segment/metric-policy partition may expose two champions.
{{ config(tags=['data_quality', 'ml_models', 'backtest']) }}

select
    target,
    grain,
    horizon,
    segment_key_json,
    metric_policy,
    count(*) as champion_count
from {{ ref('ml_model_champion') }}
where is_champion
group by target, grain, horizon, segment_key_json, metric_policy
having count(*) > 1
