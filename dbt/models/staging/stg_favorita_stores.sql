{{ config(**staging_dimension_config(unique_key='store_nbr')) }}

select *
from {{ source('favorita_raw', 'raw_favorita_stores') }}
