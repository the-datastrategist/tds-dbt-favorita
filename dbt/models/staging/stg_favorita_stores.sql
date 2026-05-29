{{ config(
    materialized='table',
    tags=['staging']
) }}

select *
from {{ source('favorita_raw', 'raw_favorita_stores') }}
