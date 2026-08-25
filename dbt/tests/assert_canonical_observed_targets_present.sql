select 'forecast_observations' as relation_name, series_key, period_start
from {{ ref('forecast_observations') }}
where target_observed and target_value is null

union all

select 'forecast_features' as relation_name, series_key, period_start
from {{ ref('forecast_features') }}
where target_observed and target_value is null

union all

select 'forecast_features_store' as relation_name, series_key, period_start
from {{ ref('forecast_features_store') }}
where target_observed and target_value is null
