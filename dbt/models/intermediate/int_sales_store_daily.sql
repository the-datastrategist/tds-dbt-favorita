{{ 
  config(
    materialized = "table",
    partition_by={'field': 'date', 'data_type': 'date'},
    cluster_by=['store_nbr'],
    tags = ["train", "features"]
    )
}}

with

favorita_train as (
  select *
  from {{ ref('stg_favorita_sales_fct') }}
),

-- Daily sales metrics for each store
store_sales_daily_agg as (
  select 
    date,
    store_nbr,
    max(data_split_source) as data_split_source,
    -- base metrics
    sum(sales)                      as sales_store,
    count(distinct product_id)      as products_store,
    count(distinct product_family)  as product_families_store,
    -- on promotion
    sum(if(on_promotion = 1, sales, 0))                         as sales_store_on_promotion,
    count(distinct if(on_promotion = 1, product_id, null))      as products_store_on_promotion,
    count(distinct if(on_promotion = 1, product_family, null))  as product_families_store_on_promotion,
  from favorita_train
  group by 1,2
),

--  Daily sales metrics for each store
store_sales_daily_window as (
  select 
    date,
    store_nbr,
    data_split_source,
    date_sub(date, interval 1 day) as feature_as_of_date,

    -- DATE TRANSFORMATIONS

    -- Date Transformations
    extract(day from date)        as day_of_month,
    extract(dayofweek from date)  as day_of_week,       -- 1 = Sunday, 7 = Saturday
    extract(week from date)       as iso_week_of_year,  -- ISO 8601 week
    extract(month from date)      as month,
    extract(quarter from date)    as quarter,
    extract(year from date)       as year,
    -- Week of Month
    ceil(extract(day from date) / 7.0) as week_of_month,
    -- ISO week date parts
    extract(isoyear from date)  as iso_year,
    extract(isoweek from date)  as iso_week,
    -- Additional custom parts
    format_date('%A', date)     as day_name,
    format_date('%B', date)     as month_name,

    -- SALES METRICS

    -- Base metrics
    sales_store,
    products_store,
    product_families_store,
    sales_store_on_promotion,
    products_store_on_promotion,
    product_families_store_on_promotion,

    -- % On Promotion
    safe_divide(sales_store_on_promotion, sales_store)                        as pct_sales_store_on_promotion,
    safe_divide(products_store_on_promotion, products_store)                  as pct_products_store_on_promotion,
    safe_divide(product_families_store_on_promotion, product_families_store)  as pct_product_families_store_on_promotion,

    -- Store sales on the same day of week one calendar week later (e.g. Mon -> next Mon)
    sum(sales_store) over (partition by store_nbr order by date rows between 7 following and 7 following)    as sales_store_n1d_same_dow,

    -- Next N-day sales (from the day after date through N days forward)
    sum(sales_store) over (partition by store_nbr order by date rows between 1 following and 1 following)    as sales_store_n1d,
    sum(sales_store) over (partition by store_nbr order by date rows between 1 following and 7 following)    as sales_store_n7d,
    sum(sales_store) over (partition by store_nbr order by date rows between 1 following and 14 following)   as sales_store_n14d,
    sum(sales_store) over (partition by store_nbr order by date rows between 1 following and 28 following)   as sales_store_n28d,
    sum(sales_store) over (partition by store_nbr order by date rows between 1 following and 30 following)   as sales_store_n30d,
    sum(sales_store) over (partition by store_nbr order by date rows between 1 following and 60 following)   as sales_store_n60d,
    sum(sales_store) over (partition by store_nbr order by date rows between 1 following and 90 following)   as sales_store_n90d,

    -- Last N-day sales (through date, inclusive)
    sales_store as sales_store_l1d,
    sum(sales_store) over (partition by store_nbr order by date rows between 2 preceding and current row)    as sales_store_l3d,
    sum(sales_store) over (partition by store_nbr order by date rows between 6 preceding and current row)    as sales_store_l7d,
    sum(sales_store) over (partition by store_nbr order by date rows between 13 preceding and current row)   as sales_store_l14d,
    sum(sales_store) over (partition by store_nbr order by date rows between 27 preceding and current row)   as sales_store_l28d,
    sum(sales_store) over (partition by store_nbr order by date rows between 29 preceding and current row)   as sales_store_l30d,
    sum(sales_store) over (partition by store_nbr order by date rows between 59 preceding and current row)   as sales_store_l60d,
    sum(sales_store) over (partition by store_nbr order by date rows between 89 preceding and current row)   as sales_store_l90d,

    -- Last N-day Average Daily Sales (through date, inclusive)
    avg(sales_store) over (partition by store_nbr order by date rows between 2 preceding and current row)    as avg_sales_store_l3d,
    avg(sales_store) over (partition by store_nbr order by date rows between 6 preceding and current row)    as avg_sales_store_l7d,
    avg(sales_store) over (partition by store_nbr order by date rows between 13 preceding and current row)   as avg_sales_store_l14d,
    avg(sales_store) over (partition by store_nbr order by date rows between 27 preceding and current row)   as avg_sales_store_l28d,
    avg(sales_store) over (partition by store_nbr order by date rows between 29 preceding and current row)   as avg_sales_store_l30d,
    avg(sales_store) over (partition by store_nbr order by date rows between 59 preceding and current row)   as avg_sales_store_l60d,
    avg(sales_store) over (partition by store_nbr order by date rows between 89 preceding and current row)   as avg_sales_store_l90d,
    avg(sales_store) over (partition by store_nbr order by date rows between 179 preceding and current row)  as avg_sales_store_l180d,
    avg(sales_store) over (partition by store_nbr order by date rows between 269 preceding and current row)  as avg_sales_store_l270d,
    avg(sales_store) over (partition by store_nbr order by date rows between 359 preceding and current row)  as avg_sales_store_l360d,

    -- Last N-day Standard Dev Daily Sales (through date, inclusive)
    stddev(sales_store) over (partition by store_nbr order by date rows between 2 preceding and current row)    as stddev_sales_store_l3d,
    stddev(sales_store) over (partition by store_nbr order by date rows between 6 preceding and current row)    as stddev_sales_store_l7d,
    stddev(sales_store) over (partition by store_nbr order by date rows between 13 preceding and current row)   as stddev_sales_store_l14d,
    stddev(sales_store) over (partition by store_nbr order by date rows between 27 preceding and current row)   as stddev_sales_store_l28d,
    stddev(sales_store) over (partition by store_nbr order by date rows between 29 preceding and current row)   as stddev_sales_store_l30d,
    stddev(sales_store) over (partition by store_nbr order by date rows between 59 preceding and current row)   as stddev_sales_store_l60d,
    stddev(sales_store) over (partition by store_nbr order by date rows between 89 preceding and current row)   as stddev_sales_store_l90d,
    stddev(sales_store) over (partition by store_nbr order by date rows between 179 preceding and current row)  as stddev_sales_store_l180d,
    stddev(sales_store) over (partition by store_nbr order by date rows between 269 preceding and current row)  as stddev_sales_store_l270d,
    stddev(sales_store) over (partition by store_nbr order by date rows between 359 preceding and current row)  as stddev_sales_store_l360d,

    -- Prior N-day sales (period immediately before each last-N window)
    sum(sales_store) over (partition by store_nbr order by date rows between 1 preceding and 1 preceding)    as sales_store_p1d,    
    sum(sales_store) over (partition by store_nbr order by date rows between 5 preceding and 3 preceding)    as sales_store_p3d,
    sum(sales_store) over (partition by store_nbr order by date rows between 13 preceding and 7 preceding)   as sales_store_p7d,
    sum(sales_store) over (partition by store_nbr order by date rows between 27 preceding and 14 preceding)  as sales_store_p14d,
    sum(sales_store) over (partition by store_nbr order by date rows between 55 preceding and 28 preceding)  as sales_store_p28d,
    sum(sales_store) over (partition by store_nbr order by date rows between 59 preceding and 30 preceding)  as sales_store_p30d,
    sum(sales_store) over (partition by store_nbr order by date rows between 119 preceding and 60 preceding) as sales_store_p60d,
    sum(sales_store) over (partition by store_nbr order by date rows between 179 preceding and 90 preceding) as sales_store_p90d,

  from store_sales_daily_agg
),

store_sales_daily_window_w_on_promotion as (
  select 
    *,
    -- Last N-day % Sales On Promotion
    avg(pct_sales_store_on_promotion) over (partition by store_nbr order by date rows between 2 preceding and current row)    as avg_pct_sales_store_on_promotion_l3d,
    avg(pct_sales_store_on_promotion) over (partition by store_nbr order by date rows between 6 preceding and current row)    as avg_pct_sales_store_on_promotion_l7d,
    avg(pct_sales_store_on_promotion) over (partition by store_nbr order by date rows between 13 preceding and current row)   as avg_pct_sales_store_on_promotion_l14d,
    avg(pct_sales_store_on_promotion) over (partition by store_nbr order by date rows between 27 preceding and current row)   as avg_pct_sales_store_on_promotion_l28d,
    avg(pct_sales_store_on_promotion) over (partition by store_nbr order by date rows between 29 preceding and current row)   as avg_pct_sales_store_on_promotion_l30d,
    avg(pct_sales_store_on_promotion) over (partition by store_nbr order by date rows between 59 preceding and current row)   as avg_pct_sales_store_on_promotion_l60d,
    avg(pct_sales_store_on_promotion) over (partition by store_nbr order by date rows between 89 preceding and current row)   as avg_pct_sales_store_on_promotion_l90d,
    avg(pct_sales_store_on_promotion) over (partition by store_nbr order by date rows between 179 preceding and current row)  as avg_pct_sales_store_on_promotion_l180d,
    avg(pct_sales_store_on_promotion) over (partition by store_nbr order by date rows between 269 preceding and current row)  as avg_pct_sales_store_on_promotion_l270d,
    avg(pct_sales_store_on_promotion) over (partition by store_nbr order by date rows between 359 preceding and current row)  as avg_pct_sales_store_on_promotion_l360d,

    -- Last N-day % Sales On Promotion
    stddev(pct_sales_store_on_promotion) over (partition by store_nbr order by date rows between 2 preceding and current row)    as stddev_pct_sales_store_on_promotion_l3d,
    stddev(pct_sales_store_on_promotion) over (partition by store_nbr order by date rows between 6 preceding and current row)    as stddev_pct_sales_store_on_promotion_l7d,
    stddev(pct_sales_store_on_promotion) over (partition by store_nbr order by date rows between 13 preceding and current row)   as stddev_pct_sales_store_on_promotion_l14d,
    stddev(pct_sales_store_on_promotion) over (partition by store_nbr order by date rows between 27 preceding and current row)   as stddev_pct_sales_store_on_promotion_l28d,
    stddev(pct_sales_store_on_promotion) over (partition by store_nbr order by date rows between 29 preceding and current row)   as stddev_pct_sales_store_on_promotion_l30d,
    stddev(pct_sales_store_on_promotion) over (partition by store_nbr order by date rows between 59 preceding and current row)   as stddev_pct_sales_store_on_promotion_l60d,
    stddev(pct_sales_store_on_promotion) over (partition by store_nbr order by date rows between 89 preceding and current row)   as stddev_pct_sales_store_on_promotion_l90d,
    stddev(pct_sales_store_on_promotion) over (partition by store_nbr order by date rows between 179 preceding and current row)  as stddev_pct_sales_store_on_promotion_l180d,
    stddev(pct_sales_store_on_promotion) over (partition by store_nbr order by date rows between 269 preceding and current row)  as stddev_pct_sales_store_on_promotion_l270d,
    stddev(pct_sales_store_on_promotion) over (partition by store_nbr order by date rows between 359 preceding and current row)  as stddev_pct_sales_store_on_promotion_l360d,

    -- Last N-day % Products On Promotion
    avg(pct_products_store_on_promotion) over (partition by store_nbr order by date rows between 2 preceding and current row)    as avg_pct_products_store_on_promotion_l3d,
    avg(pct_products_store_on_promotion) over (partition by store_nbr order by date rows between 6 preceding and current row)    as avg_pct_products_store_on_promotion_l7d,
    avg(pct_products_store_on_promotion) over (partition by store_nbr order by date rows between 13 preceding and current row)   as avg_pct_products_store_on_promotion_l14d,
    avg(pct_products_store_on_promotion) over (partition by store_nbr order by date rows between 27 preceding and current row)   as avg_pct_products_store_on_promotion_l28d,
    avg(pct_products_store_on_promotion) over (partition by store_nbr order by date rows between 29 preceding and current row)   as avg_pct_products_store_on_promotion_l30d,
    avg(pct_products_store_on_promotion) over (partition by store_nbr order by date rows between 59 preceding and current row)   as avg_pct_products_store_on_promotion_l60d,
    avg(pct_products_store_on_promotion) over (partition by store_nbr order by date rows between 89 preceding and current row)   as avg_pct_products_store_on_promotion_l90d,
    avg(pct_products_store_on_promotion) over (partition by store_nbr order by date rows between 179 preceding and current row)  as avg_pct_products_store_on_promotion_l180d,
    avg(pct_products_store_on_promotion) over (partition by store_nbr order by date rows between 269 preceding and current row)  as avg_pct_products_store_on_promotion_l270d,
    avg(pct_products_store_on_promotion) over (partition by store_nbr order by date rows between 359 preceding and current row)  as avg_pct_products_store_on_promotion_l360d,

    -- Last N-day % Sales On Promotion
    stddev(pct_products_store_on_promotion) over (partition by store_nbr order by date rows between 2 preceding and current row)    as stddev_pct_products_store_on_promotion_l3d,
    stddev(pct_products_store_on_promotion) over (partition by store_nbr order by date rows between 6 preceding and current row)    as stddev_pct_products_store_on_promotion_l7d,
    stddev(pct_products_store_on_promotion) over (partition by store_nbr order by date rows between 13 preceding and current row)   as stddev_pct_products_store_on_promotion_l14d,
    stddev(pct_products_store_on_promotion) over (partition by store_nbr order by date rows between 27 preceding and current row)   as stddev_pct_products_store_on_promotion_l28d,
    stddev(pct_products_store_on_promotion) over (partition by store_nbr order by date rows between 29 preceding and current row)   as stddev_pct_products_store_on_promotion_l30d,
    stddev(pct_products_store_on_promotion) over (partition by store_nbr order by date rows between 59 preceding and current row)   as stddev_pct_products_store_on_promotion_l60d,
    stddev(pct_products_store_on_promotion) over (partition by store_nbr order by date rows between 89 preceding and current row)   as stddev_pct_products_store_on_promotion_l90d,
    stddev(pct_products_store_on_promotion) over (partition by store_nbr order by date rows between 179 preceding and current row)  as stddev_pct_products_store_on_promotion_l180d,
    stddev(pct_products_store_on_promotion) over (partition by store_nbr order by date rows between 269 preceding and current row)  as stddev_pct_products_store_on_promotion_l270d,
    stddev(pct_products_store_on_promotion) over (partition by store_nbr order by date rows between 359 preceding and current row)  as stddev_pct_products_store_on_promotion_l360d,

    -- Last Sales for the given Day of Week, within the past N days
    avg(sales_store) over (partition by store_nbr, day_of_week order by date rows between 13 preceding and current row)   as avg_sales_store_dow_l14d,
    avg(sales_store) over (partition by store_nbr, day_of_week order by date rows between 27 preceding and current row)   as avg_sales_store_dow_l28d,
    avg(sales_store) over (partition by store_nbr, day_of_week order by date rows between 59 preceding and current row)   as avg_sales_store_dow_l60d,
    avg(sales_store) over (partition by store_nbr, day_of_week order by date rows between 89 preceding and current row)   as avg_sales_store_dow_l90d,
    avg(sales_store) over (partition by store_nbr, day_of_week order by date rows between 179 preceding and current row)  as avg_sales_store_dow_l180d,
    avg(sales_store) over (partition by store_nbr, day_of_week order by date rows between 269 preceding and current row)  as avg_sales_store_dow_l270d,
    avg(sales_store) over (partition by store_nbr, day_of_week order by date rows between 359 preceding and current row)  as avg_sales_store_dow_l360d,

  from store_sales_daily_window
),

store_sales_daily_window_comparison as (
  select
    *,

    -- Short vs Long Period Comparisons
    safe_divide(sales_store_l1d, avg_sales_store_l3d) - 1   as avg_sales_store_l1d_l3d_pct_diff,
    safe_divide(sales_store_l1d, avg_sales_store_l7d) - 1   as avg_sales_store_l1d_l7d_pct_diff,
    safe_divide(sales_store_l1d, avg_sales_store_l14d) - 1  as avg_sales_store_l1d_l14d_pct_diff,
    safe_divide(sales_store_l1d, avg_sales_store_l28d) - 1  as avg_sales_store_l1d_l28d_pct_diff,

    safe_divide(avg_sales_store_l3d, avg_sales_store_l7d) - 1   as avg_sales_store_l3d_l7d_pct_diff,
    safe_divide(avg_sales_store_l3d, avg_sales_store_l14d) - 1  as avg_sales_store_l3d_l14d_pct_diff,
    safe_divide(avg_sales_store_l3d, avg_sales_store_l28d) - 1  as avg_sales_store_l3d_l28d_pct_diff,

    safe_divide(avg_sales_store_l7d, avg_sales_store_l14d) - 1  as avg_sales_store_l7d_l14d_pct_diff,
    safe_divide(avg_sales_store_l7d, avg_sales_store_l28d) - 1  as avg_sales_store_l7d_l28d_pct_diff,
    safe_divide(avg_sales_store_l7d, avg_sales_store_l30d) - 1  as avg_sales_store_l7d_l30d_pct_diff,
    safe_divide(avg_sales_store_l7d, avg_sales_store_l60d) - 1  as avg_sales_store_l7d_l60d_pct_diff,
    safe_divide(avg_sales_store_l7d, avg_sales_store_l90d) - 1  as avg_sales_store_l7d_l90d_pct_diff,
    safe_divide(avg_sales_store_l7d, avg_sales_store_l180d) - 1  as avg_sales_store_l7d_l180d_pct_diff,
    safe_divide(avg_sales_store_l7d, avg_sales_store_l360d) - 1  as avg_sales_store_l7d_l360d_pct_diff,

    -- Period-Over-Period Comparisons
    safe_divide(sales_store_l1d, sales_store_p1d) - 1   as sales_store_l1d_p1d_pct_diff,
    safe_divide(sales_store_l3d, sales_store_p3d) - 1   as sales_store_l3d_p3d_pct_diff,
    safe_divide(sales_store_l7d, sales_store_p7d) - 1   as sales_store_l7d_p7d_pct_diff,
    safe_divide(sales_store_l14d, sales_store_p14d) - 1 as sales_store_l14d_p14d_pct_diff,
    safe_divide(sales_store_l28d, sales_store_p28d) - 1 as sales_store_l28d_p28d_pct_diff,
    safe_divide(sales_store_l30d, sales_store_p30d) - 1 as sales_store_l30d_p30d_pct_diff,
    safe_divide(sales_store_l60d, sales_store_p60d) - 1 as sales_store_l60d_p60d_pct_diff,
    safe_divide(sales_store_l90d, sales_store_p90d) - 1 as sales_store_l90d_p90d_pct_diff,

    -- Last Sales for the given Day of Week, within the past N days
    safe_divide(avg_sales_store_dow_l14d, avg_sales_store_l14d) as avg_sales_store_dow_l14d_pct_diff,
    safe_divide(avg_sales_store_dow_l28d, avg_sales_store_l28d) as avg_sales_store_dow_l28d_pct_diff,
    safe_divide(avg_sales_store_dow_l60d, avg_sales_store_l60d) as avg_sales_store_dow_l60d_pct_diff,
    safe_divide(avg_sales_store_dow_l90d, avg_sales_store_l90d) as avg_sales_store_dow_l90d_pct_diff,

    -- % Difference in Sales over Time for the given Day of Week
    safe_divide(avg_sales_store_dow_l14d, avg_sales_store_dow_l28d) as avg_sales_store_dow_l14d_l28d_diff,
    safe_divide(avg_sales_store_dow_l14d, avg_sales_store_dow_l60d) as avg_sales_store_dow_l14d_l60d_diff,
    safe_divide(avg_sales_store_dow_l14d, avg_sales_store_dow_l90d) as avg_sales_store_dow_l14d_l90d_diff,
    safe_divide(avg_sales_store_dow_l28d, avg_sales_store_dow_l60d) as avg_sales_store_dow_l28d_l60d_diff,
    safe_divide(avg_sales_store_dow_l28d, avg_sales_store_dow_l90d) as avg_sales_store_dow_l28d_l90d_diff,
    safe_divide(avg_sales_store_dow_l60d, avg_sales_store_dow_l90d) as avg_sales_store_dow_l60d_l90d_diff,

  from store_sales_daily_window_w_on_promotion
)

select *
from store_sales_daily_window_comparison
