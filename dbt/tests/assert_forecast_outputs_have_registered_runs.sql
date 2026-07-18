select outputs.*
from {{ ref('stg_forecast_outputs') }} as outputs
left join {{ ref('stg_forecast_runs') }} as runs
  on outputs.forecast_run_id = runs.forecast_run_id
where outputs.contract_enforced
  and runs.forecast_run_id is null
