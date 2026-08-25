{{ config(materialized='view', tags=['forecast_delivery', 'publication']) }}

select * except (publication_rank)
from (
    select
        published.*,
        row_number() over (
            partition by
                forecast_contract_name,
                coalesce(series_key, to_hex(sha256(entity_key_json))),
                target_date,
                horizon,
                destination
            order by published_at desc, publication_version desc, publication_id desc
        ) as publication_rank
    from {{ ref('published_forecasts_by_run') }} as published
)
where publication_rank = 1
