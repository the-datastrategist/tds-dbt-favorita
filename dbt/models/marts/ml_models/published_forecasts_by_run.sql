{{ config(materialized='view', tags=['forecast_delivery', 'publication']) }}

select
    publications.publication_id,
    publications.publication_version,
    publications.destination,
    publications.delivery_status,
    publications.published_value,
    publications.published_at,
    publications.published_by,
    runs.feature_availability_hash,
    outputs.* except (published_forecast)
from {{ ref('stg_forecast_publications') }} as publications
inner join {{ ref('stg_forecast_outputs') }} as outputs
    using (forecast_output_id, forecast_run_id)
inner join {{ ref('stg_forecast_runs') }} as runs
    using (forecast_run_id)
