{{
  config(
    materialized='view',
    tags=['canonical', 'features', 'train']
  )
}}

-- First canonical runtime migration: the configured company-day BQML model trains and scores
-- through this adapter. Legacy feature names remain as adapter payload columns so predictions are
-- behaviorally equivalent while identity and temporal roles are domain neutral.
select
    'company' as series_key,
    to_json_string(struct('company' as scope)) as entity_key_json,
    date as period_start,
    sales_company_l1d as target_value,
    sales_company_l1d is not null as target_observed,
    true as is_eligible,
    cast(null as string) as eligibility_reason,
    date as data_cutoff,
    *
from {{ ref('int_sales_daily') }}
