{{ config(
    materialized='view',
    tags=['vertex', 'staging']
) }}

/*
  One row per job_run_id (Vertex jobs upsert via MERGE).
*/
select
    job_run_id,
    config_name,
    model_family,
    model_type,
    job_step,
    status,
    vertex_job_resource,
    vertex_experiment,
    error_message,
    started_at,
    finished_at,
    duration_sec,
    row_count,
    artifact_uri,
    git_sha,
    image_uri,
    pipeline_run_id,
    optimize_run_id,
    project_id,
    region
from {{ source('vertex_ml', 'favorita_vertex_job_runs') }}
