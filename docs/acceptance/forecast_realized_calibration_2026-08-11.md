# Realized forecast calibration acceptance — 2026-08-11

Realized calibration monitoring passed controlled and live BigQuery acceptance.

The controlled dbt fixture covers four operational states:

| State | Alerting | Meaning |
|---|---|---|
| `healthy` | No | Coverage and normalized median bias are within policy. |
| `insufficient_actuals` | No | Too few target-date outcomes have landed for a reliable decision. |
| `under_coverage` | Yes | Realized P10-P90 coverage is below the configured minimum. |
| `material_bias` | Yes | Absolute normalized median bias exceeds the configured maximum. |

The default policy uses a trailing 28-day window, at least 30 realized actuals, minimum 80% P10-P90
coverage, and maximum 10% absolute normalized median bias. These values are deployment defaults,
not universal statistical guarantees, and should be tuned using client backtests.

Focused Python monitoring tests passed (`7 passed`). The focused live dbt build created
`forecast_realized_calibration` and completed its controlled fixture and schema tests successfully.
The full live monitoring selector also passed (`PASS=101`, `WARN=0`, `ERROR=0`, `SKIP=0`).
The full unit suite passed (`367 passed`, `7 deselected`).
