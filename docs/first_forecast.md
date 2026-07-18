# Generate your first forecast

This guide takes a configured environment from a fresh clone to a persisted, canonical forecast
in BigQuery. It uses the reference Favorita implementation and the local Docker execution path so
you can inspect each stage before introducing scheduling.

## What you will produce

By the end, you will have:

- validated forecast, feature-availability, model, and backtest contracts;
- project feature models in BigQuery;
- a trained model artifact in Cloud Storage;
- model predictions and a draft canonical forecast in BigQuery; and
- dbt views over the forecast run and output contracts.

This is the shortest supported path to a forecast. Model promotion, calibrated champion scoring,
hierarchical reconciliation, approval, and publication are separate operational stages. Their
current implementation status is tracked in the [engineering specs](specs/README.md).

## 1. Prepare the environment

Complete the [GCP and GitHub bootstrap](gcp_bootstrap.md) first. For local Docker execution, copy
the environment template and configure the project, datasets, buckets, and local credentials:

```bash
cp env.example .env
make bootstrap-check
make docker-build
```

GitHub Actions uses keyless Workload Identity Federation. Local Docker commands use the credential
path configured in `.env`; do not commit that file or the credential JSON.

Verify BigQuery connectivity and install dbt packages:

```bash
make dbt-debug
make dbt-deps
```

## 2. Review the platform contracts

Before running data or models, review these project adaptation points:

| Contract | File | Defines |
|---|---|---|
| Forecast | `vertex/config/forecast_contract.yaml` | Target, grain, frequency, horizons, quantiles, and hierarchy |
| Feature availability | `vertex/config/feature_availability.yaml` | Point-in-time classes, lags, cutoffs, and versions |
| Model | `vertex/config/model_config.yaml` | Feature queries, target, model family, artifacts, and output tables |
| Backtest | `vertex/config/backtest_contract.yaml` | Rolling origins, baselines, metrics, and promotion gates |

Validate the configured models and inspect the rolling-origin plan without writing data:

```bash
make vertex-validate-configs
make vertex-backtest-plan
```

The default one-day training and prediction commands use `favorita_store_n1d_xgboost`. The default
backtest uses `favorita_store_h7_xgboost`, a genuinely horizon-aware seven-day model. Do not replace
the horizon-7 model with the one-day model unless you also change the contract.

## 3. Load data and build features

The reference loader expects the demo source files in `GCS_RAW_DATA_BUCKET`:

```bash
# Optional, write-free preview
make load-favorita-bigquery ARGS="--dry-run"

# Load the reference source data
make load-favorita-bigquery

# Build staging, intermediate features, and non-BQML marts
make dbt-run
make dbt-test
```

For another business, replace the loader and dbt source/feature models while preserving the
platform contracts. See [Forecast contract](forecast_contract.md) and
[Feature availability](feature_availability.md).

## 4. Create the forecast tables

Apply the idempotent BigQuery DDL before the first Vertex run:

```bash
make vertex-bq-ddl
```

This creates the model metadata tables and the canonical `forecast_runs` and `forecast_outputs`
contracts. Re-running the command is safe; schema evolution uses `IF NOT EXISTS` operations.

## 5. Train and predict

Run the reference model inside the project Docker image:

```bash
make vertex-train VERTEX_CONFIG=favorita_store_n1d_xgboost
make vertex-predict VERTEX_CONFIG=favorita_store_n1d_xgboost
```

Training writes the model artifact and immutable metadata. Prediction loads the trained artifact,
writes model-oriented prediction rows, and writes canonical forecast rows when
`outputs.forecast_output_table` is configured.

To use managed Vertex AI compute instead, configure `VERTEX_TRAINING_IMAGE` and the staging bucket,
then submit and wait:

```bash
make vertex-train VERTEX_CONFIG=favorita_store_n1d_xgboost VERTEX_MODE=vertex SYNC=1
make vertex-predict VERTEX_CONFIG=favorita_store_n1d_xgboost VERTEX_MODE=vertex SYNC=1
```

## 6. Build the consumption views

Stage the Vertex and forecast contracts through dbt:

```bash
make dbt-vertex
make dbt-run ARGS="--select stg_forecast_runs stg_forecast_outputs"
```

Inspect direct first-run results through `stg_forecast_runs` and `stg_forecast_outputs`.
`forecast_visible_drafts` is the consumer boundary for the scheduled pipeline; build and use it
only after the governed lifecycle and scheduled draft path are configured, because it deliberately
excludes direct prediction runs and partial pipeline writes.

## 7. Verify the result

Run these queries in BigQuery, replacing the project and dataset if you changed the defaults:

```sql
select
  forecast_run_id,
  forecast_contract_name,
  run_type,
  run_status,
  forecast_origin,
  row_count,
  finished_at
from `tds-favorita.favorita.forecast_runs`
order by started_at desc
limit 10;
```

```sql
select
  forecast_run_id,
  target_date,
  horizon,
  entity_key_json,
  prediction_p10,
  prediction_p50,
  prediction_p90,
  statistical_forecast,
  forecast_status,
  model_id,
  data_cutoff
from `tds-favorita.favorita.forecast_outputs`
order by created_at desc
limit 100;
```

Check that horizons match the contract, `data_cutoff` does not exceed the forecast origin, model
and code provenance are populated, and initial outputs have `forecast_status = 'draft'`.

## 8. Evaluate before operational publication

Run and persist the configured ML-versus-baseline rolling-origin evaluation:

```bash
make vertex-backtest-persist
make dbt-backtest
```

This compares the ML model with the configured naive and intermittent-demand baselines through the
same append-only prediction and metric contracts. See [Backtesting and evaluation](backtesting_and_evaluation.md).

The scheduled forecast flow is available for development after a governed champion and required
calibration/reconciliation inputs exist:

```bash
make prefect-flow-scheduled-forecast
```

That flow currently creates a validated, atomically visible draft. Planner approval, publication,
delivery integrations, and full operational SLO coverage remain roadmap work; consult the
[specification status table](specs/README.md) before treating those stages as production-complete.

## Where to go next

- [Vertex model guide](../vertex/README.md) — configure models and managed jobs.
- [Orchestration guide](../orchestration/README.md) — deploy and schedule Prefect flows.
- [Forecasting methods](forecasting_methods.md) — baselines, calibration, and strategy routing.
- [Infrastructure operations](iac.md) — IAM, environments, monitoring, and recovery.
- [Engineering specs](specs/README.md) — accepted capabilities and remaining roadmap work.
