-- stg_favorita_sales_fct is train ∪ test with aligned columns (test sales null).
{{ config(tags=['data_quality', 'staging']) }}

with counts as (
    select
        (select count(*) from {{ ref('stg_favorita_sales_fct') }}) as fct_count,
        (
            (select count(*) from {{ ref('stg_favorita_train') }})
            + (select count(*) from {{ ref('stg_favorita_test') }})
        ) as parts_count
)

select *
from counts
where fct_count != parts_count
