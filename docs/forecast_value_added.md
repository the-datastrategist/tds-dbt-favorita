# Forecast Value Added

Forecast Value Added (FVA) shows whether a forecast-processing step reduces error relative to a
simpler reference. For error metrics such as WAPE, positive FVA means the candidate improved the
forecast:

```text
FVA points = reference error - candidate error
FVA ratio  = (reference error - candidate error) / reference error
```

## Backtest comparisons

`forecast_value_added_backtest` compares every candidate with the benchmark configured in
`fva_benchmark_by_grain`. Comparisons use the same backtest run, origin, horizon, segment, eligible
population, and prediction count. A missing benchmark, population mismatch, or missing metric
returns a non-comparable status and null FVA rather than a misleading score.

Use positive and negative results to identify where ML or another baseline adds or destroys value:

```sql
select horizon, candidate_name, avg(wape_fva_points) as average_wape_fva_points
from `tds-favorita.favorita.forecast_value_added_backtest`
where comparison_status = 'comparable'
group by horizon, candidate_name
order by horizon, average_wape_fva_points desc;
```

## Operational comparisons

`forecast_value_added_operations` compares statistical, planner-adjusted, and published WAPE for
each publication version after actual demand arrives. It reports planner, reason code, horizon, and
destination. The reference implementation resolves store-day actuals from
`int_demand_store_daily`; other grains must add an explicit actuals adapter before use.

Rows remain `awaiting_actuals` or `incomplete_actuals` until every forecast in the comparison has an
actual. FVA fields remain null for those rows. Do not aggregate non-comparable rows into an FVA
score.

## Interpretation

- Positive `planner_wape_fva_points`: the selected planner adjustment improved on the statistical
  forecast.
- Negative `planner_wape_fva_points`: the adjustment reduced accuracy.
- Positive `publication_wape_fva_points`: publication processing improved on the approved value.
- Positive `total_wape_fva_points`: the published value improved on the statistical forecast.

FVA is diagnostic evidence, not an automatic reason to reject an override. Business constraints
may justify a locally negative accuracy result, so retain the reason code and evaluate repeated
patterns across origins.
