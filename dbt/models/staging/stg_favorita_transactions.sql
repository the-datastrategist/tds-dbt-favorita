{{ config(
    materialized = "view",
    tags = ["staging"]
) }}

select *
from {{ source('favorita_raw', 'raw_favorita_transactions') }}
