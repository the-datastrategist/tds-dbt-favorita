{{ config(materialized='view', tags=['forecast_delivery', 'audit']) }}

select *
from {{ ref('stg_forecast_publication_events') }}
