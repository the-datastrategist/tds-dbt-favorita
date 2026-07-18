{{ config(materialized='view', tags=['vertex', 'staging', 'backtest', 'lifecycle']) }}

select
    candidate_id,
    model_scope_json,
    to_json_string(model_scope_json) as model_scope_key,
    model_config_name,
    model_family,
    model_type,
    backtest_run_id,
    backtest_contract_hash,
    artifact_uri,
    initial_state,
    registered_by,
    registered_at,
    created_at
from {{ source('vertex_ml', 'model_candidates') }}
