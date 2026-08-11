# Forecast Value Added acceptance — 2026-08-11

The FVA marts passed live acceptance in `tds-favorita.favorita`.

## Results

- `make forecast-fva-build` created both views and completed with
  `PASS=14 WARN=0 ERROR=0 SKIP=0`.
- The backtest mart returned 60 candidate comparisons against `seasonal_naive_7d`:
  - 16 added value;
  - 24 destroyed value;
  - 10 were neutral;
  - 10 were rejected as population mismatches and exposed null FVA.
- The operations mart returned five publication groups as `awaiting_actuals`. This is expected for
  the demonstrative dataset: target-date actuals are not yet present, and the mart correctly keeps
  operational FVA null rather than treating missing actuals as zero demand.
- Fixture tests proved positive FVA direction, population mismatch rejection, planner attribution,
  and incomplete-actual coverage behavior.

## Result

**Accepted.** Backtest FVA is immediately queryable. Operational FVA becomes comparable
automatically when matching actuals arrive; missing actuals fail closed.
