{{ config(materialized='view', tags=['forecast_contract', 'monitoring']) }}

select
    eligibility_decision_id,
    forecast_run_id,
    eligibility_snapshot_id,
    forecast_contract_name,
    forecast_contract_hash,
    forecast_origin,
    entity_key_json,
    target_date,
    horizon,
    is_eligible,
    ineligibility_reason,
    has_exception,
    decision_evidence_json,
    decided_at
from {{ source('vertex_ml', 'forecast_eligibility_decisions') }}
