{{ config(materialized='view', tags=['forecast_delivery', 'publication', 'audit']) }}

select
    publications.publication_id,
    publications.idempotency_key,
    publications.forecast_output_id,
    publications.forecast_run_id,
    outputs.forecast_contract_name,
    outputs.forecast_contract_hash,
    publications.approval_id,
    approvals.override_id,
    publications.publication_version,
    publications.destination,
    publications.delivery_status,
    publications.delivery_reference,
    publications.published_value,
    publications.published_at,
    publications.published_by,
    approvals.decided_at,
    approvals.decided_by,
    revisions.revision_id,
    revisions.prior_publication_id,
    revisions.replacement_publication_id,
    revisions.revision_type,
    revisions.reason_code as revision_reason_code,
    revisions.revised_at,
    revisions.revised_by
from {{ ref('stg_forecast_publications') }} as publications
inner join {{ ref('stg_forecast_outputs') }} as outputs
    using (forecast_output_id, forecast_run_id)
inner join {{ ref('stg_forecast_approvals') }} as approvals
    using (approval_id, forecast_output_id, forecast_run_id)
left join {{ ref('stg_forecast_revisions') }} as revisions
    on publications.publication_id = revisions.prior_publication_id
    or publications.publication_id = revisions.replacement_publication_id
