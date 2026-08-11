{{ config(materialized='view', tags=['forecast_delivery', 'forecast_operations', 'audit']) }}

select
    overrides.*,
    outputs.forecast_contract_name,
    outputs.forecast_contract_hash,
    outputs.entity_key_json,
    outputs.forecast_origin,
    outputs.target_date,
    outputs.horizon,
    outputs.prediction_p50 as statistical_forecast,
    approvals.approval_id,
    approvals.decision,
    approvals.approved_value,
    approvals.decided_at,
    approvals.decided_by
from {{ ref('stg_forecast_overrides') }} as overrides
inner join {{ ref('stg_forecast_outputs') }} as outputs
    using (forecast_output_id, forecast_run_id)
left join {{ ref('stg_forecast_approvals') }} as approvals
    using (override_id, forecast_output_id, forecast_run_id)
