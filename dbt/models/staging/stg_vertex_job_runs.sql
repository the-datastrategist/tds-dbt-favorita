{{ config(
    materialized='view',
    tags=['vertex', 'staging']
) }}

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
    project_id,
    region
from {{ source('vertex_ml', 'favorita_vertex_job_runs') }}
