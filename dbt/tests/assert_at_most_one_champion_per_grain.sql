-- ml_model_champion must flag exactly one champion per grain; a tie or a ranking bug
-- would surface as more than one is_champion=true row for the same grain.
{{ config(tags=['data_quality', 'ml_models']) }}

select
    grain,
    count(*) as champion_count
from {{ ref('ml_model_champion') }}
where is_champion
group by grain
having count(*) > 1
