{{ config(materialized='view', tags=['forecast_contract', 'publication']) }}

select outputs.*
from {{ ref('stg_forecast_outputs') }} as outputs
inner join {{ ref('stg_forecast_runs') }} as runs
    using (forecast_run_id, forecast_contract_name, forecast_contract_hash)
where runs.run_status in ('draft', 'approved', 'published')
    and outputs.forecast_status in ('draft', 'approved', 'published')
