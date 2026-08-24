-- Canonical adapters must not expose information newer than the represented period.
select series_key, period_start, data_cutoff
from {{ ref('forecast_observations') }}
where data_cutoff > period_start

union all

select series_key, period_start, data_cutoff
from {{ ref('forecast_features') }}
where data_cutoff > period_start

union all

select series_key, period_start, data_cutoff
from {{ ref('forecast_eligibility') }}
where data_cutoff > period_start
