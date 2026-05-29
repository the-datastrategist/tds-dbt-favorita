-- Daily company sales in int_sales_daily must match staged train aggregates.
{{ config(tags=['data_quality', 'features']) }}

with staged as (
    select
        date,
        sum(sales) as sales_company_staged
    from {{ ref('stg_favorita_train') }}
    group by 1
),

intermediate as (
    select
        date,
        sales_company_l1d as sales_company_int
    from {{ ref('int_sales_daily') }}
)

select
    coalesce(staged.date, intermediate.date) as date,
    staged.sales_company_staged,
    intermediate.sales_company_int
from staged
full outer join intermediate
    on staged.date = intermediate.date
where staged.date is null
    or intermediate.date is null
    or abs(staged.sales_company_staged - intermediate.sales_company_int) > 0.001
