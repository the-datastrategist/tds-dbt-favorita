{{ config(materialized='view', tags=['forecast_operations', 'fva', 'backtest']) }}

with metrics as (
    select * from {{ ref('stg_backtest_metrics') }}
), benchmarks as (
    select *
    from metrics
    where baseline_name = case grain
        {% for grain, benchmark in var('fva_benchmark_by_grain', {}).items() %}
        when '{{ grain }}' then '{{ benchmark }}'
        {% endfor %}
        else null
    end
), comparisons as (
    select
        candidate.backtest_run_id,
        candidate.backtest_contract_name,
        candidate.backtest_contract_hash,
        candidate.model_config_name,
        candidate.model_family,
        candidate.model_type,
        candidate.target,
        candidate.grain,
        candidate.forecast_origin,
        candidate.horizon,
        candidate.segment_key_json,
        benchmark.baseline_name as benchmark_name,
        candidate.baseline_name as candidate_name,
        candidate.baseline_name = candidate.model_config_name as is_ml_candidate,
        benchmark.eligible_count as benchmark_eligible_count,
        candidate.eligible_count as candidate_eligible_count,
        benchmark.prediction_count as benchmark_prediction_count,
        candidate.prediction_count as candidate_prediction_count,
        benchmark.wape as benchmark_wape,
        candidate.wape as candidate_wape,
        benchmark.mae as benchmark_mae,
        candidate.mae as candidate_mae,
        benchmark.bias as benchmark_bias,
        candidate.bias as candidate_bias,
        benchmark.prediction_completeness as benchmark_prediction_completeness,
        candidate.prediction_completeness as candidate_prediction_completeness,
        case
            when benchmark.metric_id is null then 'missing_benchmark'
            when benchmark.eligible_count != candidate.eligible_count
                or benchmark.prediction_count != candidate.prediction_count
                then 'population_mismatch'
            when benchmark.wape is null or candidate.wape is null
                or benchmark.mae is null or candidate.mae is null
                then 'missing_metrics'
            else 'comparable'
        end as comparison_status
    from metrics as candidate
    left join benchmarks as benchmark
        on candidate.backtest_run_id = benchmark.backtest_run_id
        and candidate.forecast_origin = benchmark.forecast_origin
        and candidate.horizon = benchmark.horizon
        and candidate.segment_key_json = benchmark.segment_key_json
    where candidate.baseline_name != coalesce(benchmark.baseline_name, '')
)
select
    *,
    if(comparison_status = 'comparable', round(benchmark_wape - candidate_wape, 12), null)
        as wape_fva_points,
    if(
        comparison_status = 'comparable',
        round(safe_divide(benchmark_wape - candidate_wape, benchmark_wape), 12),
        null
    ) as wape_fva_ratio,
    if(comparison_status = 'comparable', round(benchmark_mae - candidate_mae, 12), null)
        as mae_fva,
    case
        when comparison_status != 'comparable' then null
        when candidate_wape < benchmark_wape then 'value_added'
        when candidate_wape > benchmark_wape then 'value_destroyed'
        else 'neutral'
    end as fva_status
from comparisons
