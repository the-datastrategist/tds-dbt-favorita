# Forecast pipeline cost acceptance — 2026-08-11

The normalized cost-evidence contract and pipeline-cost monitoring mart passed controlled and live
BigQuery acceptance.

`forecast_cost_events` is an append-only provider-independent USD contract. Cost collectors record
service, cost type, usage window, run/model/stage/environment attribution, optional usage units,
BigQuery bytes and slots, and source identity. `source_system + source_event_id` produces a stable
event ID, making retries idempotent.

`forecast_pipeline_cost` evaluates the latest run per contract and any unattributed events. Defaults
ticket run cost above $25, cost per thousand outputs above $2, historical cost above twice the prior
average after three runs, and missing required allocation labels. No evidence and insufficient
history are explicit non-alerting readiness states.

Validation completed:

- Additive BigQuery DDL created `forecast_cost_events`.
- Staging build and eight schema tests passed (`PASS=11`, `ERROR=0`).
- The focused mart build, two controlled fixtures, and five schema tests passed
  (`PASS=10`, `ERROR=0`).
- Focused writer and alert tests passed (`15 passed`).
- Python formatting, import-order, and lint checks passed.
- The complete monitoring selector passed (`PASS=128`, `WARN=0`, `ERROR=0`, `SKIP=0`).
- The full unit suite passed (`378 passed`, `7 deselected`) with 76.44% coverage.
- A live query returned one platform sentinel with zero events, `cost_data_unavailable`, and
  `is_alerting=false`.

The controlled fixtures prove anomaly, unit-budget, missing-label, insufficient-history, and
no-evidence behavior. The live sentinel is expected because the demonstration dataset is static and
no billing-export collector is active; it represents unavailable evidence, not zero spend.
Production collection can use `scripts/record_forecast_cost.py` directly or adapt Cloud Billing
export rows to the same contract.
The live evaluator loaded the empty cost mart without emitting a cost alert; its only dry-run events
were existing pipeline-health alerts for forecast runs that predate eligibility evidence.
