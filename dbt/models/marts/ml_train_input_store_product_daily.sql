{{ 
  config(
    materialized = "table",
    partition_by={'field': 'date', 'data_type': 'date'},
    cluster_by=['store_nbr', 'product_id'],
    tags = ["train", "features"]
    )
}}


with

favorita_train as (
  select *
  from {{ source('favorita_stg', 'stg_favorita_train') }}
),

-- Daily sales aggregated by store and product
store_sales_daily_agg as (
  select 
    date,
    store_nbr,
    product_id,
    sum(sales)  as sales_store_product,
    sum(if(on_promotion = 1, sales, 0))  as sales_store_product_on_promotion,
  from favorita_train
  group by 1,2,3
),

-- Daily sales aggregated by store and product with date transformations
store_sales_daily_window as (
  select 
    date,
    store_nbr,
    product_id,
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
    sales_store_product,
    sales_store_product_on_promotion,

    -- % On Promotion
    safe_divide(sales_store_product_on_promotion, sales_store_product)  as pct_sales_store_product_on_promotion,

    -- Last N-day sales
    sales_store_product                                                                                                          as sales_store_product_l1d,
    sum(sales_store_product) over (partition by store_nbr, product_id order by date rows between 3 preceding and 1 preceding)    as sales_store_product_l3d,
    sum(sales_store_product) over (partition by store_nbr, product_id order by date rows between 7 preceding and 1 preceding)    as sales_store_product_l7d,
    sum(sales_store_product) over (partition by store_nbr, product_id order by date rows between 14 preceding and 1 preceding)   as sales_store_product_l14d,
    sum(sales_store_product) over (partition by store_nbr, product_id order by date rows between 28 preceding and 1 preceding)   as sales_store_product_l28d,
    sum(sales_store_product) over (partition by store_nbr, product_id order by date rows between 30 preceding and 1 preceding)   as sales_store_product_l30d,
    sum(sales_store_product) over (partition by store_nbr, product_id order by date rows between 60 preceding and 1 preceding)   as sales_store_product_l60d,
    sum(sales_store_product) over (partition by store_nbr, product_id order by date rows between 90 preceding and 1 preceding)   as sales_store_product_l90d,

    -- Last N-day Average Daily Sales
    avg(sales_store_product) over (partition by store_nbr, product_id order by date rows between 3 preceding and 1 preceding)    as avg_sales_store_product_l3d,
    avg(sales_store_product) over (partition by store_nbr, product_id order by date rows between 7 preceding and 1 preceding)    as avg_sales_store_product_l7d,
    avg(sales_store_product) over (partition by store_nbr, product_id order by date rows between 14 preceding and 1 preceding)   as avg_sales_store_product_l14d,
    avg(sales_store_product) over (partition by store_nbr, product_id order by date rows between 28 preceding and 1 preceding)   as avg_sales_store_product_l28d,
    avg(sales_store_product) over (partition by store_nbr, product_id order by date rows between 30 preceding and 1 preceding)   as avg_sales_store_product_l30d,
    avg(sales_store_product) over (partition by store_nbr, product_id order by date rows between 60 preceding and 1 preceding)   as avg_sales_store_product_l60d,
    avg(sales_store_product) over (partition by store_nbr, product_id order by date rows between 90 preceding and 1 preceding)   as avg_sales_store_product_l90d,
    avg(sales_store_product) over (partition by store_nbr, product_id order by date rows between 180 preceding and 1 preceding)  as avg_sales_store_product_l180d,
    avg(sales_store_product) over (partition by store_nbr, product_id order by date rows between 270 preceding and 1 preceding)  as avg_sales_store_product_l270d,
    avg(sales_store_product) over (partition by store_nbr, product_id order by date rows between 360 preceding and 1 preceding)  as avg_sales_store_product_l360d,

    -- Last N-day Standard Dev Daily Sales
    stddev(sales_store_product) over (partition by store_nbr, product_id order by date rows between 3 preceding and 1 preceding)    as stddev_sales_store_product_l3d,
    stddev(sales_store_product) over (partition by store_nbr, product_id order by date rows between 7 preceding and 1 preceding)    as stddev_sales_store_product_l7d,
    stddev(sales_store_product) over (partition by store_nbr, product_id order by date rows between 14 preceding and 1 preceding)   as stddev_sales_store_product_l14d,
    stddev(sales_store_product) over (partition by store_nbr, product_id order by date rows between 28 preceding and 1 preceding)   as stddev_sales_store_product_l28d,
    stddev(sales_store_product) over (partition by store_nbr, product_id order by date rows between 30 preceding and 1 preceding)   as stddev_sales_store_product_l30d,
    stddev(sales_store_product) over (partition by store_nbr, product_id order by date rows between 60 preceding and 1 preceding)   as stddev_sales_store_product_l60d,
    stddev(sales_store_product) over (partition by store_nbr, product_id order by date rows between 90 preceding and 1 preceding)   as stddev_sales_store_product_l90d,
    stddev(sales_store_product) over (partition by store_nbr, product_id order by date rows between 180 preceding and 1 preceding)  as stddev_sales_store_product_l180d,
    stddev(sales_store_product) over (partition by store_nbr, product_id order by date rows between 270 preceding and 1 preceding)  as stddev_sales_store_product_l270d,
    stddev(sales_store_product) over (partition by store_nbr, product_id order by date rows between 360 preceding and 1 preceding)  as stddev_sales_store_product_l360d,

    -- Prior N-day sales
    sum(sales_store_product) over (partition by store_nbr, product_id order by date rows between 2 preceding and 1 preceding)    as sales_store_product_p1d,    
    sum(sales_store_product) over (partition by store_nbr, product_id order by date rows between 5 preceding and 3 preceding)    as sales_store_product_p3d,
    sum(sales_store_product) over (partition by store_nbr, product_id order by date rows between 13 preceding and 7 preceding)   as sales_store_product_p7d,
    sum(sales_store_product) over (partition by store_nbr, product_id order by date rows between 27 preceding and 14 preceding)  as sales_store_product_p14d,
    sum(sales_store_product) over (partition by store_nbr, product_id order by date rows between 55 preceding and 28 preceding)  as sales_store_product_p28d,
    sum(sales_store_product) over (partition by store_nbr, product_id order by date rows between 59 preceding and 30 preceding)  as sales_store_product_p30d,
    sum(sales_store_product) over (partition by store_nbr, product_id order by date rows between 119 preceding and 60 preceding) as sales_store_product_p60d,
    sum(sales_store_product) over (partition by store_nbr, product_id order by date rows between 179 preceding and 90 preceding) as sales_store_product_p90d,

  from store_sales_daily_agg
),

-- Daily sales aggregated by store and product with date transformations and on promotion metrics
store_sales_daily_window_w_on_promotion as (
  select 
    *,
    -- Last N-day % Sales On Promotion
    avg(pct_sales_store_product_on_promotion) over (partition by store_nbr, product_id order by date rows between 3 preceding and 1 preceding)    as avg_pct_sales_store_product_on_promotion_l3d,
    avg(pct_sales_store_product_on_promotion) over (partition by store_nbr, product_id order by date rows between 7 preceding and 1 preceding)    as avg_pct_sales_store_product_on_promotion_l7d,
    avg(pct_sales_store_product_on_promotion) over (partition by store_nbr, product_id order by date rows between 14 preceding and 1 preceding)   as avg_pct_sales_store_product_on_promotion_l14d,
    avg(pct_sales_store_product_on_promotion) over (partition by store_nbr, product_id order by date rows between 28 preceding and 1 preceding)   as avg_pct_sales_store_product_on_promotion_l28d,
    avg(pct_sales_store_product_on_promotion) over (partition by store_nbr, product_id order by date rows between 30 preceding and 1 preceding)   as avg_pct_sales_store_product_on_promotion_l30d,
    avg(pct_sales_store_product_on_promotion) over (partition by store_nbr, product_id order by date rows between 60 preceding and 1 preceding)   as avg_pct_sales_store_product_on_promotion_l60d,
    avg(pct_sales_store_product_on_promotion) over (partition by store_nbr, product_id order by date rows between 90 preceding and 1 preceding)   as avg_pct_sales_store_product_on_promotion_l90d,
    avg(pct_sales_store_product_on_promotion) over (partition by store_nbr, product_id order by date rows between 180 preceding and 1 preceding)  as avg_pct_sales_store_product_on_promotion_l180d,
    avg(pct_sales_store_product_on_promotion) over (partition by store_nbr, product_id order by date rows between 270 preceding and 1 preceding)  as avg_pct_sales_store_product_on_promotion_l270d,
    avg(pct_sales_store_product_on_promotion) over (partition by store_nbr, product_id order by date rows between 360 preceding and 1 preceding)  as avg_pct_sales_store_product_on_promotion_l360d,

    -- Last N-day % Sales On Promotion
    stddev(pct_sales_store_product_on_promotion) over (partition by store_nbr, product_id order by date rows between 3 preceding and 1 preceding)    as stddev_pct_sales_store_product_on_promotion_l3d,
    stddev(pct_sales_store_product_on_promotion) over (partition by store_nbr, product_id order by date rows between 7 preceding and 1 preceding)    as stddev_pct_sales_store_product_on_promotion_l7d,
    stddev(pct_sales_store_product_on_promotion) over (partition by store_nbr, product_id order by date rows between 14 preceding and 1 preceding)   as stddev_pct_sales_store_product_on_promotion_l14d,
    stddev(pct_sales_store_product_on_promotion) over (partition by store_nbr, product_id order by date rows between 28 preceding and 1 preceding)   as stddev_pct_sales_store_product_on_promotion_l28d,
    stddev(pct_sales_store_product_on_promotion) over (partition by store_nbr, product_id order by date rows between 30 preceding and 1 preceding)   as stddev_pct_sales_store_product_on_promotion_l30d,
    stddev(pct_sales_store_product_on_promotion) over (partition by store_nbr, product_id order by date rows between 60 preceding and 1 preceding)   as stddev_pct_sales_store_product_on_promotion_l60d,
    stddev(pct_sales_store_product_on_promotion) over (partition by store_nbr, product_id order by date rows between 90 preceding and 1 preceding)   as stddev_pct_sales_store_product_on_promotion_l90d,
    stddev(pct_sales_store_product_on_promotion) over (partition by store_nbr, product_id order by date rows between 180 preceding and 1 preceding)  as stddev_pct_sales_store_product_on_promotion_l180d,
    stddev(pct_sales_store_product_on_promotion) over (partition by store_nbr, product_id order by date rows between 270 preceding and 1 preceding)  as stddev_pct_sales_store_product_on_promotion_l270d,
    stddev(pct_sales_store_product_on_promotion) over (partition by store_nbr, product_id order by date rows between 360 preceding and 1 preceding)  as stddev_pct_sales_store_product_on_promotion_l360d,

    -- Last Sales for the given Day of Week, within the past N days
    avg(sales_store_product) over (partition by store_nbr, product_id, day_of_week order by date rows between 14 preceding and 1 preceding)   as avg_sales_store_product_dow_l14d,
    avg(sales_store_product) over (partition by store_nbr, product_id, day_of_week order by date rows between 28 preceding and 1 preceding)   as avg_sales_store_product_dow_l28d,
    avg(sales_store_product) over (partition by store_nbr, product_id, day_of_week order by date rows between 60 preceding and 1 preceding)   as avg_sales_store_product_dow_l60d,
    avg(sales_store_product) over (partition by store_nbr, product_id, day_of_week order by date rows between 90 preceding and 1 preceding)   as avg_sales_store_product_dow_l90d,
    avg(sales_store_product) over (partition by store_nbr, product_id, day_of_week order by date rows between 180 preceding and 1 preceding)  as avg_sales_store_product_dow_l180d,
    avg(sales_store_product) over (partition by store_nbr, product_id, day_of_week order by date rows between 270 preceding and 1 preceding)  as avg_sales_store_product_dow_l270d,
    avg(sales_store_product) over (partition by store_nbr, product_id, day_of_week order by date rows between 360 preceding and 1 preceding)  as avg_sales_store_product_dow_l360d,

  from store_sales_daily_window
),

-- Daily sales aggregated by store and product with date transformations and on promotion metrics
store_sales_daily_window_comparison as (
  select
    *,

    -- Short vs Long Period Comparisons
    safe_divide(sales_store_product_l1d, avg_sales_store_product_l3d) - 1   as avg_sales_store_product_l1d_l3d_pct_diff,
    safe_divide(sales_store_product_l1d, avg_sales_store_product_l7d) - 1   as avg_sales_store_product_l1d_l7d_pct_diff,
    safe_divide(sales_store_product_l1d, avg_sales_store_product_l14d) - 1  as avg_sales_store_product_l1d_l14d_pct_diff,
    safe_divide(sales_store_product_l1d, avg_sales_store_product_l28d) - 1  as avg_sales_store_product_l1d_l28d_pct_diff,

    safe_divide(avg_sales_store_product_l3d, avg_sales_store_product_l7d) - 1   as avg_sales_store_product_l3d_l7d_pct_diff,
    safe_divide(avg_sales_store_product_l3d, avg_sales_store_product_l14d) - 1  as avg_sales_store_product_l3d_l14d_pct_diff,
    safe_divide(avg_sales_store_product_l3d, avg_sales_store_product_l28d) - 1  as avg_sales_store_product_l3d_l28d_pct_diff,

    safe_divide(avg_sales_store_product_l7d, avg_sales_store_product_l14d) - 1  as avg_sales_store_product_l7d_l14d_pct_diff,
    safe_divide(avg_sales_store_product_l7d, avg_sales_store_product_l28d) - 1  as avg_sales_store_product_l7d_l28d_pct_diff,
    safe_divide(avg_sales_store_product_l7d, avg_sales_store_product_l30d) - 1  as avg_sales_store_product_l7d_l30d_pct_diff,
    safe_divide(avg_sales_store_product_l7d, avg_sales_store_product_l60d) - 1  as avg_sales_store_product_l7d_l60d_pct_diff,
    safe_divide(avg_sales_store_product_l7d, avg_sales_store_product_l90d) - 1  as avg_sales_store_product_l7d_l90d_pct_diff,
    safe_divide(avg_sales_store_product_l7d, avg_sales_store_product_l180d) - 1  as avg_sales_store_product_l7d_l180d_pct_diff,
    safe_divide(avg_sales_store_product_l7d, avg_sales_store_product_l360d) - 1  as avg_sales_store_product_l7d_l360d_pct_diff,

    -- Period-Over-Period Comparisons
    safe_divide(sales_store_product_l1d, sales_store_product_p1d) - 1   as sales_store_product_l1d_p1d_pct_diff,
    safe_divide(sales_store_product_l3d, sales_store_product_p3d) - 1   as sales_store_product_l3d_p3d_pct_diff,
    safe_divide(sales_store_product_l7d, sales_store_product_p7d) - 1   as sales_store_product_l7d_p7d_pct_diff,
    safe_divide(sales_store_product_l14d, sales_store_product_p14d) - 1 as sales_store_product_l14d_p14d_pct_diff,
    safe_divide(sales_store_product_l28d, sales_store_product_p28d) - 1 as sales_store_product_l28d_p28d_pct_diff,
    safe_divide(sales_store_product_l30d, sales_store_product_p30d) - 1 as sales_store_product_l30d_p30d_pct_diff,
    safe_divide(sales_store_product_l60d, sales_store_product_p60d) - 1 as sales_store_product_l60d_p60d_pct_diff,
    safe_divide(sales_store_product_l90d, sales_store_product_p90d) - 1 as sales_store_product_l90d_p90d_pct_diff,

    -- Last Sales for the given Day of Week, within the past N days
    safe_divide(avg_sales_store_product_dow_l14d, avg_sales_store_product_l14d) as avg_sales_store_product_dow_l14d_pct_diff,
    safe_divide(avg_sales_store_product_dow_l28d, avg_sales_store_product_l28d) as avg_sales_store_product_dow_l28d_pct_diff,
    safe_divide(avg_sales_store_product_dow_l60d, avg_sales_store_product_l60d) as avg_sales_store_product_dow_l60d_pct_diff,
    safe_divide(avg_sales_store_product_dow_l90d, avg_sales_store_product_l90d) as avg_sales_store_product_dow_l90d_pct_diff,

    -- % Difference in Sales over Time for the given Day of Week
    safe_divide(avg_sales_store_product_dow_l14d, avg_sales_store_product_dow_l28d) as avg_sales_store_product_dow_l14d_l28d_diff,
    safe_divide(avg_sales_store_product_dow_l14d, avg_sales_store_product_dow_l60d) as avg_sales_store_product_dow_l14d_l60d_diff,
    safe_divide(avg_sales_store_product_dow_l14d, avg_sales_store_product_dow_l90d) as avg_sales_store_product_dow_l14d_l90d_diff,
    safe_divide(avg_sales_store_product_dow_l28d, avg_sales_store_product_dow_l60d) as avg_sales_store_product_dow_l28d_l60d_diff,
    safe_divide(avg_sales_store_product_dow_l28d, avg_sales_store_product_dow_l90d) as avg_sales_store_product_dow_l28d_l90d_diff,
    safe_divide(avg_sales_store_product_dow_l60d, avg_sales_store_product_dow_l90d) as avg_sales_store_product_dow_l60d_l90d_diff,

  from store_sales_daily_window_w_on_promotion
)

select *
from store_sales_daily_window_comparison
