-- Test period starts the day after training ends and spans 15 days (Kaggle rules).
{{ config(tags=['data_quality', 'staging']) }}

with bounds as (
    select
        (select max(date) from {{ ref('stg_favorita_train') }}) as max_train_date,
        (select min(date) from {{ ref('stg_favorita_test') }}) as min_test_date,
        (select count(distinct date) from {{ ref('stg_favorita_test') }}) as test_day_count
)

select *
from bounds
where min_test_date != date_add(max_train_date, interval 1 day)
    or test_day_count != 15
