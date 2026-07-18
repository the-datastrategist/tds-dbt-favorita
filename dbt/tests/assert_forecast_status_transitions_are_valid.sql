select *
from {{ ref('stg_forecast_status_history') }}
where not (
  (previous_status is null and new_status in ('draft', 'failed'))
  or (previous_status = 'draft' and new_status in ('approved', 'superseded', 'failed'))
  or (previous_status = 'approved' and new_status in ('published', 'superseded', 'failed'))
  or (previous_status = 'published' and new_status = 'superseded')
)
