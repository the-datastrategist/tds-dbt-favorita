{{ config(materialized='view', tags=['forecast_operations', 'staging']) }}

select
    revision_id,
    idempotency_key,
    forecast_output_id,
    forecast_run_id,
    prior_publication_id,
    replacement_publication_id,
    revision_type,
    reason_code,
    comment,
    revised_at,
    revised_by,
    created_at
from {{ source('vertex_ml', 'forecast_revisions') }}
