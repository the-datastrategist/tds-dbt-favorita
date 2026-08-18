{{ config(materialized='view', tags=['monitoring']) }}

{% set maximum_run_usd = var('cost_maximum_run_usd', 25.0) %}
{% set maximum_per_thousand_rows_usd = var('cost_maximum_per_thousand_rows_usd', 2.0) %}
{% set anomaly_multiplier = var('cost_anomaly_multiplier', 2.0) %}
{% set minimum_historical_runs = var('cost_minimum_historical_runs', 3) %}

with runs as (
    select
        forecast_run_id,
        forecast_contract_name,
        started_at,
        row_count as output_row_count
    from {{ ref('stg_forecast_runs') }}
), event_costs as (
    select
        coalesce(nullif(trim(forecast_run_id), ''), concat('unattributed:', cost_event_id))
            as cost_scope_key,
        forecast_run_id,
        forecast_contract_name,
        model_run_id,
        stage_name,
        environment,
        service_name,
        cost_type,
        amount_usd,
        bytes_processed,
        slot_ms,
        usage_start_at,
        case
            when nullif(trim(forecast_contract_name), '') is null then 1 else 0
        end
        + case when nullif(trim(forecast_run_id), '') is null then 1 else 0 end
        + case when nullif(trim(stage_name), '') is null then 1 else 0 end
        + case when nullif(trim(environment), '') is null then 1 else 0 end
            as missing_required_label_count
    from {{ ref('stg_forecast_cost_events') }}
), aggregated as (
    select
        cost_scope_key,
        any_value(forecast_run_id) as forecast_run_id,
        any_value(forecast_contract_name) as forecast_contract_name,
        any_value(model_run_id) as model_run_id,
        any_value(environment) as environment,
        min(usage_start_at) as usage_start_at,
        count(*) as cost_event_count,
        count(distinct service_name) as service_count,
        count(distinct stage_name) as stage_count,
        sum(amount_usd) as total_cost_usd,
        sum(if(lower(service_name) like '%bigquery%', amount_usd, 0)) as bigquery_cost_usd,
        sum(if(lower(service_name) like '%vertex%', amount_usd, 0)) as vertex_cost_usd,
        sum(coalesce(bytes_processed, 0)) as bytes_processed,
        sum(coalesce(slot_ms, 0)) as slot_ms,
        sum(missing_required_label_count) as missing_required_label_count
    from event_costs
    group by cost_scope_key
), attributed as (
    select
        costs.* except (forecast_contract_name),
        coalesce(costs.forecast_contract_name, runs.forecast_contract_name) as forecast_contract_name,
        runs.started_at as forecast_started_at,
        runs.output_row_count,
        safe_divide(costs.total_cost_usd * 1000, nullif(runs.output_row_count, 0))
            as cost_per_thousand_rows_usd
    from aggregated costs
    left join runs using (forecast_run_id)
), history as (
    select
        *,
        count(*) over (
            partition by forecast_contract_name
            order by forecast_started_at, forecast_run_id
            rows between unbounded preceding and 1 preceding
        ) as historical_run_count,
        avg(total_cost_usd) over (
            partition by forecast_contract_name
            order by forecast_started_at, forecast_run_id
            rows between unbounded preceding and 1 preceding
        ) as historical_average_run_cost_usd,
        row_number() over (
            partition by forecast_contract_name
            order by forecast_started_at desc, forecast_run_id desc
        ) as latest_run_rank
    from attributed
    where forecast_run_id is not null and forecast_contract_name is not null
), monitored as (
    select * except (latest_run_rank)
    from history
    where latest_run_rank = 1
    union all
    select
        unattributed.*,
        0 as historical_run_count,
        cast(null as numeric) as historical_average_run_cost_usd
    from attributed unattributed
    where forecast_run_id is null or forecast_contract_name is null
), evaluated as (
    select
        *,
        {{ maximum_run_usd }} as maximum_run_cost_usd,
        {{ maximum_per_thousand_rows_usd }} as maximum_cost_per_thousand_rows_usd,
        {{ anomaly_multiplier }} as cost_anomaly_multiplier,
        {{ minimum_historical_runs }} as minimum_historical_run_count,
        case
            when missing_required_label_count > 0 then 'missing_required_labels'
            when total_cost_usd > {{ maximum_run_usd }} then 'over_run_budget'
            when cost_per_thousand_rows_usd > {{ maximum_per_thousand_rows_usd }}
                then 'over_unit_budget'
            when historical_run_count >= {{ minimum_historical_runs }}
                and total_cost_usd > historical_average_run_cost_usd * {{ anomaly_multiplier }}
                then 'cost_anomaly'
            when historical_run_count < {{ minimum_historical_runs }} then 'insufficient_history'
            else 'healthy'
        end as cost_status
    from monitored
), available as (
    select
        *,
        cost_status not in ('healthy', 'insufficient_history') as is_alerting
    from evaluated
), unavailable as (
    select
        'platform' as cost_scope_key,
        cast(null as string) as forecast_run_id,
        cast(null as string) as model_run_id,
        cast(null as string) as environment,
        cast(null as timestamp) as usage_start_at,
        0 as cost_event_count,
        0 as service_count,
        0 as stage_count,
        cast(null as numeric) as total_cost_usd,
        cast(null as numeric) as bigquery_cost_usd,
        cast(null as numeric) as vertex_cost_usd,
        0 as bytes_processed,
        0 as slot_ms,
        0 as missing_required_label_count,
        cast(null as string) as forecast_contract_name,
        cast(null as timestamp) as forecast_started_at,
        cast(null as int64) as output_row_count,
        cast(null as numeric) as cost_per_thousand_rows_usd,
        0 as historical_run_count,
        cast(null as numeric) as historical_average_run_cost_usd,
        {{ maximum_run_usd }} as maximum_run_cost_usd,
        {{ maximum_per_thousand_rows_usd }} as maximum_cost_per_thousand_rows_usd,
        {{ anomaly_multiplier }} as cost_anomaly_multiplier,
        {{ minimum_historical_runs }} as minimum_historical_run_count,
        'cost_data_unavailable' as cost_status,
        false as is_alerting
    from (select 1)
    where not exists (select 1 from event_costs)
)
select * from available
union all
select * from unavailable
