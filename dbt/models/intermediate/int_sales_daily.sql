{{ 
  config(
    materialized = "table",
    partition_by={'field': 'date', 'data_type': 'date'},
    tags = ["train", "features"]
    )
}}

with

company_sales_daily_agg as (
  select 
    date,
    max(data_split_source) as data_split_source,
    sum(sales) as sales_company
  from {{ ref('stg_favorita_sales_fct') }}
  group by 1
),

company_sales_daily_window as (
  select 
    date,
    date_sub(date, interval 1 day) as feature_as_of_date,
    data_split_source,

    -- Date Transformations
      EXTRACT(DAY FROM date)        AS day_of_month,
      EXTRACT(DAYOFWEEK FROM date)  AS day_of_week,         -- 1 = Sunday, 7 = Saturday
      EXTRACT(WEEK FROM date)       AS iso_week_of_year,         -- ISO 8601 week
      EXTRACT(MONTH FROM date)      AS month,
      EXTRACT(QUARTER FROM date)    AS quarter,
      EXTRACT(YEAR FROM date)       AS year,

      -- Week of Month
      CEIL(EXTRACT(DAY FROM date) / 7.0) AS week_of_month,

      -- ISO week date parts
      EXTRACT(ISOYEAR FROM date) AS iso_year,
      EXTRACT(ISOWEEK FROM date) AS iso_week,

      -- Additional custom parts
      FORMAT_DATE('%A', date) AS day_name,
      FORMAT_DATE('%B', date) AS month_name,

      -- Data Split Source
      data_split_source,

      -- Next N-day sales
      sum(sales_company) over (order by date rows between 1 preceding and 1 preceding)    as sales_company_n1d,
      sum(sales_company) over (order by date rows between 7 preceding and 1 preceding)    as sales_company_n7d,
      sum(sales_company) over (order by date rows between 14 preceding and 1 preceding)   as sales_company_n14d,
      sum(sales_company) over (order by date rows between 28 preceding and 1 preceding)   as sales_company_n28d,
      sum(sales_company) over (order by date rows between 30 preceding and 1 preceding)   as sales_company_n30d,
      sum(sales_company) over (order by date rows between 60 preceding and 1 preceding)   as sales_company_n60d,
      sum(sales_company) over (order by date rows between 90 preceding and 1 preceding)   as sales_company_n90d,

      -- Last N-day sales
      sales_company as sales_company_l1d,
      sum(sales_company) over (order by date rows between 3 preceding and 1 preceding)    as sales_company_l3d,
      sum(sales_company) over (order by date rows between 7 preceding and 1 preceding)    as sales_company_l7d,
      sum(sales_company) over (order by date rows between 14 preceding and 1 preceding)   as sales_company_l14d,
      sum(sales_company) over (order by date rows between 28 preceding and 1 preceding)   as sales_company_l28d,
      sum(sales_company) over (order by date rows between 30 preceding and 1 preceding)   as sales_company_l30d,
      sum(sales_company) over (order by date rows between 60 preceding and 1 preceding)   as sales_company_l60d,
      sum(sales_company) over (order by date rows between 90 preceding and 1 preceding)   as sales_company_l90d,

      -- Last N-day Average Daily Sales
      avg(sales_company) over (order by date rows between 3 preceding and 1 preceding)    as avg_sales_company_l3d,
      avg(sales_company) over (order by date rows between 7 preceding and 1 preceding)    as avg_sales_company_l7d,
      avg(sales_company) over (order by date rows between 14 preceding and 1 preceding)   as avg_sales_company_l14d,
      avg(sales_company) over (order by date rows between 28 preceding and 1 preceding)   as avg_sales_company_l28d,
      avg(sales_company) over (order by date rows between 30 preceding and 1 preceding)   as avg_sales_company_l30d,
      avg(sales_company) over (order by date rows between 60 preceding and 1 preceding)   as avg_sales_company_l60d,
      avg(sales_company) over (order by date rows between 90 preceding and 1 preceding)   as avg_sales_company_l90d,
      avg(sales_company) over (order by date rows between 180 preceding and 1 preceding)  as avg_sales_company_l180d,
      avg(sales_company) over (order by date rows between 270 preceding and 1 preceding)  as avg_sales_company_l270d,
      avg(sales_company) over (order by date rows between 360 preceding and 1 preceding)  as avg_sales_company_l360d,

      -- Last N-day Standard Dev Daily Sales
      stddev(sales_company) over (order by date rows between 3 preceding and 1 preceding)    as stddev_sales_company_l3d,
      stddev(sales_company) over (order by date rows between 7 preceding and 1 preceding)    as stddev_sales_company_l7d,
      stddev(sales_company) over (order by date rows between 14 preceding and 1 preceding)   as stddev_sales_company_l14d,
      stddev(sales_company) over (order by date rows between 28 preceding and 1 preceding)   as stddev_sales_company_l28d,
      stddev(sales_company) over (order by date rows between 30 preceding and 1 preceding)   as stddev_sales_company_l30d,
      stddev(sales_company) over (order by date rows between 60 preceding and 1 preceding)   as stddev_sales_company_l60d,
      stddev(sales_company) over (order by date rows between 90 preceding and 1 preceding)   as stddev_sales_company_l90d,
      stddev(sales_company) over (order by date rows between 180 preceding and 1 preceding)  as stddev_sales_company_l180d,
      stddev(sales_company) over (order by date rows between 270 preceding and 1 preceding)  as stddev_sales_company_l270d,
      stddev(sales_company) over (order by date rows between 360 preceding and 1 preceding)  as stddev_sales_company_l360d,

      -- Prior N-day sales
      sum(sales_company) over (order by date rows between 2 preceding and 1 preceding)    as sales_company_p1d,    
      sum(sales_company) over (order by date rows between 5 preceding and 3 preceding)    as sales_company_p3d,
      sum(sales_company) over (order by date rows between 13 preceding and 7 preceding)   as sales_company_p7d,
      sum(sales_company) over (order by date rows between 27 preceding and 14 preceding)  as sales_company_p14d,
      sum(sales_company) over (order by date rows between 55 preceding and 28 preceding)  as sales_company_p28d,
      sum(sales_company) over (order by date rows between 59 preceding and 30 preceding)  as sales_company_p30d,
      sum(sales_company) over (order by date rows between 119 preceding and 60 preceding) as sales_company_p60d,
      sum(sales_company) over (order by date rows between 179 preceding and 90 preceding) as sales_company_p90d,

  from company_sales_daily_agg
),

company_sales_daily_window_comparison as (
  select
    *,

    -- Short vs Long Period Comparisons
    safe_divide(sales_company_l1d, avg_sales_company_l3d) - 1   as avg_sales_company_l1d_l3d_pct_diff,
    safe_divide(sales_company_l1d, avg_sales_company_l7d) - 1   as avg_sales_company_l1d_l7d_pct_diff,
    safe_divide(sales_company_l1d, avg_sales_company_l14d) - 1  as avg_sales_company_l1d_l14d_pct_diff,
    safe_divide(sales_company_l1d, avg_sales_company_l28d) - 1  as avg_sales_company_l1d_l28d_pct_diff,

    safe_divide(avg_sales_company_l3d, avg_sales_company_l7d) - 1   as avg_sales_company_l3d_l7d_pct_diff,
    safe_divide(avg_sales_company_l3d, avg_sales_company_l14d) - 1  as avg_sales_company_l3d_l14d_pct_diff,
    safe_divide(avg_sales_company_l3d, avg_sales_company_l28d) - 1  as avg_sales_company_l3d_l28d_pct_diff,

    safe_divide(avg_sales_company_l7d, avg_sales_company_l14d) - 1  as avg_sales_company_l7d_l14d_pct_diff,
    safe_divide(avg_sales_company_l7d, avg_sales_company_l28d) - 1  as avg_sales_company_l7d_l28d_pct_diff,
    safe_divide(avg_sales_company_l7d, avg_sales_company_l30d) - 1  as avg_sales_company_l7d_l30d_pct_diff,
    safe_divide(avg_sales_company_l7d, avg_sales_company_l60d) - 1  as avg_sales_company_l7d_l60d_pct_diff,
    safe_divide(avg_sales_company_l7d, avg_sales_company_l90d) - 1  as avg_sales_company_l7d_l90d_pct_diff,
    safe_divide(avg_sales_company_l7d, avg_sales_company_l180d) - 1  as avg_sales_company_l7d_l180d_pct_diff,
    safe_divide(avg_sales_company_l7d, avg_sales_company_l360d) - 1  as avg_sales_company_l7d_l360d_pct_diff,

    -- Period-Over-Period Comparisons
    safe_divide(sales_company_l1d, sales_company_p1d) - 1   as sales_company_l1d_p1d_pct_diff,
    safe_divide(sales_company_l3d, sales_company_p3d) - 1   as sales_company_l3d_p3d_pct_diff,
    safe_divide(sales_company_l7d, sales_company_p7d) - 1   as sales_company_l7d_p7d_pct_diff,
    safe_divide(sales_company_l14d, sales_company_p14d) - 1 as sales_company_l14d_p14d_pct_diff,
    safe_divide(sales_company_l28d, sales_company_p28d) - 1 as sales_company_l28d_p28d_pct_diff,
    safe_divide(sales_company_l30d, sales_company_p30d) - 1 as sales_company_l30d_p30d_pct_diff,
    safe_divide(sales_company_l60d, sales_company_p60d) - 1 as sales_company_l60d_p60d_pct_diff,
    safe_divide(sales_company_l90d, sales_company_p90d) - 1 as sales_company_l90d_p90d_pct_diff,

  from company_sales_daily_window
)

select *
from company_sales_daily_window_comparison
