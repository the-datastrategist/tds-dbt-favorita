# Forecast eligibility evidence acceptance — 2026-08-11

Immutable eligibility evidence passed local and live acceptance.

The pipeline test fixture froze two candidates, admitted one, excluded one with
`insufficient_history`, and produced exactly one forecast. The population gate reconciled:

| Measure | Count |
|---|---:|
| Candidates | 2 |
| Eligible | 1 |
| Predicted | 1 |
| Excluded | 1 |
| Exceptions | 0 |

`make test-unit` completed with 362 passed tests and 75.84% coverage. The additive BigQuery DDL
created `forecast_eligibility_decisions` and added candidate/eligible/excluded/exception counts to
`forecast_runs`. After rebuilding `stg_forecast_runs`, `make selector-forecast-monitoring`
completed live with `PASS=93`, `WARN=0`, `ERROR=0`, including the controlled exclusion unit test
and all eligibility-ledger schema and health-status tests.

Existing historical runs have no retroactive ledger. `forecast_pipeline_health` intentionally
reports `missing_eligibility_evidence` for such a latest run until the next scheduled pipeline run
persists the new evidence.
