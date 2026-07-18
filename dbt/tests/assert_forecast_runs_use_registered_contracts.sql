select runs.*
from {{ ref('stg_forecast_runs') }} as runs
left join {{ ref('stg_forecast_contracts') }} as contracts
  on runs.forecast_contract_name = contracts.forecast_contract_name
 and runs.forecast_contract_hash = contracts.forecast_contract_hash
where contracts.forecast_contract_hash is null
