select series_key, period_start, is_eligible, eligibility_reason
from {{ ref('forecast_eligibility') }}
where (is_eligible and eligibility_reason is not null)
   or (not is_eligible and eligibility_reason is null)
