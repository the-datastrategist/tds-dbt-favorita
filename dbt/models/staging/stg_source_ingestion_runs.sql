{{ config(materialized='view', tags=['monitoring', 'staging']) }}

select
    ingestion_run_id,
    source_name,
    source_policy_hash,
    data_mode,
    status,
    started_at,
    finished_at,
    source_watermark,
    ingested_row_count,
    table_count,
    source_uri,
    source_table,
    watermark_column,
    expected_interval_hours,
    allowed_lateness_hours,
    evaluate_on_json,
    code_sha,
    error_message,
    details_json,
    created_at
from {{ source('vertex_ml', 'source_ingestion_runs') }}
