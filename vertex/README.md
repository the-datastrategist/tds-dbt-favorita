# Vertex AI — custom model training

Python training, prediction, and hyperparameter optimization for Favorita forecasting. Jobs are driven by **`config/model_config.yaml`**, executed locally in Docker or submitted as **Vertex AI Custom Jobs**.

For dbt, data loading, and the full repo workflow, see the [root README](../README.md).

## Architecture

```text
model_config.yaml  →  vertex.jobs.run  →  registry (model_type × step)  →  model scripts
                              ↓
                    BigQuery (metadata, predictions, job runs)
                    GCS (model artifacts + manifest.json)
```

| Step | Config example | What it does |
|------|----------------|--------------|
| `train` | `favorita_store_n1d_xgboost` | Fit model, write GCS artifacts + metadata/performance to BigQuery |
| `predict` | `favorita_store_n1d_xgboost` | Load latest (or pinned) artifact, write unified rows to `favorita_model_predictions` |
| `optimize` | `favorita_store_n1d_xgboost` | Optuna trials → `favorita_model_optimize` |

Configs that share **`model_family`** (e.g. `favorita_store_daily`) are meant to be used together: train writes artifacts; predict references `inputs.artifact_config_name` to find them.

**Optimize → train:** After Optuna, best hyperparameters are written to  
`gs://<bucket>/optimize/<optimize_config_name>/latest_best_params.json`. Train configs set  
`inputs.optimize_config_name` (or infer `*_train` → `*_optimize`) and merge those params over  
`inputs.model_params` unless `use_optimized_params: false`.

## Directory layout

```text
vertex/
├── config/
│   ├── model_config.yaml    # Job specs (defaults + named configs)
│   └── load_config.py       # Merge defaults, validate per step
├── jobs/
│   ├── run.py               # Entrypoint: load config → registry → runner
│   └── submit.py            # Submit Custom Job that runs run.py in GCP
├── models/
│   ├── registry.py          # (model_type, step) → train/predict/optimize
│   └── xgboost/             # XGBoost train, predict, optimize
├── utils/                   # BigQuery, GCS artifacts, predictions schema, tracking
├── ddl/
│   └── vertex_bq_tables.sql # One-time BigQuery table DDL
└── tests/                   # pytest (unit)
```

## Prerequisites

1. **GCP**
   - APIs: BigQuery, Cloud Storage, Vertex AI
   - Service account with BigQuery read/write and GCS read/write on your model bucket
   - Credentials JSON mounted for Docker (see root README)

2. **BigQuery tables** (run once; re-run after DDL changes)

   ```bash
   make vertex-bq-ddl
   ```

   This applies [`ddl/vertex_bq_tables.sql`](ddl/vertex_bq_tables.sql) (`CREATE TABLE` + idempotent `ALTER TABLE` migrations). Tables:

   - `favorita_vertex_job_runs` — orchestration audit
   - `favorita_model_metadata` — training lineage
   - `favorita_model_performance` — holdout metrics
   - `favorita_model_optimize` — hyperparameter trials
   - `favorita_model_predictions` — unified prediction fact table

3. **Feature data** — training SQL in config usually points at dbt marts (e.g. `int_sales_store_daily`). Build features with dbt before training:

   ```bash
   make dbt-run-model MODEL=int_sales_store_daily
   ```

4. **Docker image** (local Docker or Vertex container)

   ```bash
   make docker-build
   ```

   For **Vertex submit**, push the image and set `VERTEX_TRAINING_IMAGE` (see below).

## Configuration

All jobs use **`config/model_config.yaml`**.

- **`defaults`** — shared `project_id`, `region`, and output table IDs
- **`configs`** — named blocks with `job.step`, `job.model_type`, `model_family`, `inputs`, `outputs`, optional `vertex` block

Example train block (abbreviated):

```yaml
- name: favorita_store_n1d_xgboost
  model_family: favorita_store_daily
  job:
    step: train
    model_type: xgboost
  inputs:
    train_sql_query: |
      SELECT * FROM `project.dataset.int_sales_store_daily`
      WHERE data_split_source = 'train'
    predict_sql_query: |
      SELECT * FROM `project.dataset.int_sales_store_daily`
      WHERE data_split_source = 'test'
    target_column: sales_store
    entity_column: store_nbr
    id_columns: [store_nbr]
    excluded_columns: [store_nbr, date, sales_store_l1d]
    gcs_model_path: gs://your-bucket/models/
  outputs: {}   # inherits metadata_table, etc. from defaults
```

Predict config must set **`inputs.artifact_config_name`** to the train config name (e.g. `favorita_store_n1d_xgboost`) unless you pin **`inputs.model_run_id`**.

Validate a single config:

```bash
make vertex-validate-config MODEL=favorita_store_n1d_xgboost
```

## Running jobs (Makefile)

From the **repository root**. Default **`VERTEX_MODE=docker`** runs `vertex.jobs.run` inside the project image on your machine.

| Command | Description |
|---------|-------------|
| `make vertex-train` | Train (default config: `favorita_store_n1d_xgboost`) |
| `make vertex-predict` | Predict (`favorita_store_n1d_xgboost`) |
| `make vertex-optimize` | Optuna search (`favorita_store_n1d_xgboost`) |
| `make mlflow-ui` | MLflow UI for local runs in `./mlruns` (http://127.0.0.1:5001) |
| `make vertex-train VERTEX_MODE=vertex` | Submit training **Custom Job** to Vertex AI |
| `make vertex-train VERTEX_MODE=vertex SYNC=1` | Submit and wait until the job finishes |

Explicit targets:

| Docker (local machine) | Vertex AI submit |
|------------------------|------------------|
| `vertex-train-docker` | `vertex-submit-train` |
| `vertex-predict-docker` | `vertex-submit-predict` |
| `vertex-optimize-docker` | `vertex-submit-optimize` |

Run **any** named config:

```bash
make vertex-run-docker VERTEX_CONFIG_NAME=favorita_store_n1d_xgboost
make vertex-submit VERTEX_CONFIG_NAME=favorita_store_n1d_xgboost SYNC=1
```

Legacy aliases still work: `make model-train` → `vertex-train-docker`, etc.

Override default config names:

```bash
make vertex-train VERTEX_TRAIN_CONFIG=my_custom_train
```

### Walk-forward backfill

Point-in-time **train → predict** for each anchor date (targets such as `sales_store_n1d` — next-day sales from features at `date`). Logic lives in `config/backfill.py` and `jobs/backfill.py`; the same `run_backfill()` function is used by the Prefect flow in `orchestration/flows/backfill.py`.

| Train SQL | `date` in `(as_of - train_days, as_of - 1]` (labels observed) |
| Predict SQL | `date = as_of` |

```bash
# Inspect generated SQL
make vertex-backfill START_DATE=2016-08-01 END_DATE=2016-08-03 DRY_RUN=1

# Run (default config: favorita_store_n1d_xgboost)
make vertex-backfill START_DATE=2016-08-01 END_DATE=2016-08-31 INTERVAL_DAYS=1 TRAIN_DAYS=180

# Dev: cap iterations
make vertex-backfill START_DATE=2016-08-01 END_DATE=2016-08-31 MAX_ITERATIONS=2
```

Each iteration pins `inputs.model_run_id` on predict so artifacts do not cross dates. Predictions append to `favorita_model_predictions`.

## Running on Vertex AI

1. Set in **`.env`** (see `env.example`):

   ```bash
   GOOGLE_PROJECT_ID=your-project
   VERTEX_AI_REGION=us-central1
   VERTEX_AI_STAGING_BUCKET=gs://your-bucket/vertex-staging
   VERTEX_TRAINING_IMAGE=us-central1-docker.pkg.dev/your-project/repo/tds-favorita:latest
   ```

2. Build, tag, and push the image your project uses for training.

3. Submit:

   ```bash
   make vertex-submit-train
   # or
   make vertex-train VERTEX_MODE=vertex
   ```

The Custom Job runs: `python -m vertex.jobs.run --config-name <name>`. Job runs are **upserted** (MERGE) into **`favorita_vertex_job_runs`** — one row per `job_run_id` with duration, artifact URI, git SHA, and image URI when BigQuery is reachable. Submit passes `VERTEX_JOB_RUN_ID` so submitter and container share the same id.

## Experiment tracking

**Experiment tracking** (train, predict, optimize via `vertex.jobs.run`):

| Destination | What is logged |
|-------------|----------------|
| **BigQuery** | Training metadata (`favorita_model_metadata`), performance, predictions, optimize trials, job runs (existing runners) |
| **MLflow** | Params, metrics, tags per job run; on **train**, a **`gcs_model_catalog.json`** artifact pointing at GCS (`manifest_gcs_uri`, `joblib_gcs_uri`) |
| **Vertex AI Experiments** | Same params/metrics under `vertex.experiment` (default `favorita-vertex`) |

### GCS canonical + MLflow catalog

**Model binaries stay on GCS** (`inputs.gcs_model_path` → `manifest.json` + `model.joblib`). **`make vertex-predict`** loads from GCS via the manifest — not from MLflow.

On each successful **train** job, MLflow records a **catalog pointer**:

| Artifact / param | Purpose |
|------------------|---------|
| `gcs_model_catalog.json` | JSON sidecar on the MLflow run (default `catalog_artifacts: true`) |
| `manifest_gcs_uri`, `joblib_gcs_uri` | Run params (also in BigQuery metadata) |
| `models:/<name>/<version>` | Optional Model Registry entry when `register_model: true` |

The registered pyfunc model is a **lightweight pointer** (kilobytes in `./mlruns` or your tracking store), not a second copy of the joblib on GCS.

Enable Model Registry catalog (optional):

```yaml
defaults:
  mlflow:
    catalog_artifacts: true
    register_model: true                    # or MLFLOW_REGISTER_MODEL=true in .env
    registered_model_prefix: favorita       # → favorita-<config_name>
    registered_model_name: my-model         # optional override
```

Or per config under `mlflow:` on a train block.

Disable with `EXPERIMENT_TRACKING_ENABLED=false`. Other `defaults.mlflow` keys:

```yaml
defaults:
  mlflow:
    enabled: true
    experiment_name: favorita-vertex
    vertex_experiments: true
    catalog_artifacts: true
    register_model: false
    registered_model_prefix: favorita
    # tracking_uri: gs://your-bucket/mlflow
```

Optional per-config overrides under `vertex:` (Vertex AI **serving** registry — separate from MLflow):

```yaml
vertex:
  experiment: favorita-vertex
  machine_type: n1-standard-4
  staging_bucket: gs://...   # else VERTEX_AI_STAGING_BUCKET
  image: us-central1-docker.pkg.dev/...   # else VERTEX_TRAINING_IMAGE
  register_model: false      # Vertex AI Model Registry upload (GCS artifact for endpoints)
```

Vertex AI Model Registry upload uses `artifacts.register_from_manifest` when `vertex.register_model: true`, not the legacy `VertexModelSaver` path.

### View MLflow runs locally

After `make vertex-train`, `make vertex-predict`, or `make vertex-optimize`, runs appear under `./mlruns/` (gitignored). Start the UI from the repo root:

```bash
make mlflow-ui    # http://127.0.0.1:5001
```

Default host port **5001** avoids macOS AirPlay on **5000**. Override with `make mlflow-ui MLFLOW_UI_PORT=5002`. The Make target passes `--backend-store-uri` from `MLFLOW_TRACKING_URI` in `.env` or defaults to `file:/app/mlruns` (same directory via the `/app` bind mount).

Each job run logs `job_run_id` as an MLflow tag/param; BigQuery stores `mlflow_run_id` and `vertex_experiment_run` on `favorita_vertex_job_runs` for cross-system joins.

For Prefect orchestration UI (`make prefect-ui` on port **4200**), see the [root README](../README.md#local-uis-mlflow--prefect) and [orchestration/README.md](../orchestration/README.md).

## Running without Make

**Docker** (same as `vertex-run-docker`):

```bash
docker run --rm -v "$(pwd)":/app -w /app \
  -e PYTHONPATH=/app \
  -e GOOGLE_PROJECT_ID="$GOOGLE_PROJECT_ID" \
  -e GOOGLE_APPLICATION_CREDENTIALS=/app/credentials/your-key.json \
  -v "$(pwd)/credentials/your-key.json":/app/credentials/your-key.json:ro \
  tds-favorita:latest \
  python -m vertex.jobs.run \
  --config-path vertex/config/model_config.yaml \
  --config-name favorita_store_n1d_xgboost
```

**Docker Compose** (same as Makefile / `docker compose`):

```bash
docker compose run --rm ml-pipeline python -m vertex.jobs.run \
  --config-name favorita_store_n1d_xgboost
docker compose run --rm ml-pipeline python -m vertex.jobs.submit \
  --config-name favorita_store_n1d_xgboost --sync
```

## Artifacts and IDs

Training writes under:

```text
gs://<bucket>/<prefix>/<artifact_config_name>/xgboost_sklearn_<config_name>_<timestamp>/
  model.json
  model.joblib
  manifest.json
```

**`manifest.json`** holds `model_run_id`, `model_id`, `features`, and `parameters`. Predict uses it to align features and stamp rows.

Prediction rows (all model types) share one schema, including:

`prediction_id`, `predict_run_id`, `model_run_id`, `model_id`, `config_name`, `model_family`, `model_type`, entity/date columns, `prediction`.

Implemented in `utils/predictions.py`.

## Tests

```bash
# From repo root
make test-unit

# Or inside Docker after docker-build
docker run --rm -v "$(pwd)":/app -w /app tds-favorita:latest \
  python -m pytest vertex/tests -m unit -o addopts=
```

## Supported model types

| `job.model_type` | Module | Artifact | Notes |
|------------------|--------|----------|--------|
| `xgboost` | `models/xgboost/` | `model.json` + joblib | Tabular features |
| `random_forest` | `models/sklearn/` | joblib | Same feature path as XGBoost |
| `arima` | `models/timeseries/` | joblib bundle per entity | `inputs.entity_column`, `min_train_obs` |
| `sarima` | `models/timeseries/` | joblib bundle per entity | `seasonal_order` in `model_params` |

Example configs:

| Step | XGBoost | Random Forest | ARIMA | SARIMA |
|------|---------|---------------|-------|--------|
| Train | `favorita_store_n1d_xgboost` | `favorita_store_n1d_rf` | `favorita_store_n1d_arima` | `favorita_store_n1d_sarima` |
| Predict | `favorita_store_n1d_xgboost` | `favorita_store_n1d_rf` | `favorita_store_n1d_arima` | `favorita_store_n1d_sarima` |
| Optimize | `favorita_store_n1d_xgboost` | `favorita_store_n1d_rf` | `favorita_store_n1d_arima` | `favorita_store_n1d_sarima` |

```bash
make vertex-train VERTEX_TRAIN_CONFIG=favorita_store_n1d_xgboost
make vertex-predict VERTEX_PREDICT_CONFIG=favorita_store_n1d_xgboost
make vertex-optimize VERTEX_OPTIMIZE_CONFIG=favorita_store_n1d_xgboost
```

### Time-series predict scopes

Set `inputs.predict_scope` on predict configs:

- **`holdout`** (default): chronological test split per entity; one prediction per holdout row.
- **`forward`**: `forecast_horizon` steps beyond each entity’s last date in the scoring SQL (sets `forecast_date` on output rows).

Other useful inputs: `min_train_obs`, `max_entities` (cap entities for dev/tuning), `model_params.order`, `model_params.seasonal_order`.

## Pipelines (KFP) and dbt staging

End-to-end **optimize → train → predict** runs as a Vertex AI **PipelineJob**. Each step is a container that calls `python -m vertex.jobs.run` with config names from `model_config.yaml` (`pipelines:` block). The **container image is baked in at compile time** (`VERTEX_TRAINING_IMAGE` or `--training-image`); optional steps are included per pipeline `steps` and `--skip-optimize` / `--skip-predict`.

| Pipeline | Model | Steps |
|----------|-------|-------|
| `favorita_xgboost` | XGBoost | optimize, train, predict |
| `favorita_random_forest` | Random Forest | optimize, train, predict |
| `favorita_arima` | ARIMA | train, predict (no optimize) |

```bash
# Compile KFP JSON (checked in CI; artifacts gitignored)
make vertex-pipeline-compile VERTEX_PIPELINE=favorita_xgboost

# Submit to Vertex (requires GCP creds + VERTEX_TRAINING_IMAGE)
make vertex-pipeline-submit VERTEX_PIPELINE=favorita_xgboost VERTEX_MODE=vertex

# Train-only pipeline (skip tuning and scoring)
make vertex-pipeline-train-only VERTEX_PIPELINE=favorita_arima

# Stage Vertex outputs in BigQuery for analytics
make dbt-vertex
```

**GCP practices** (consulting template): dedicated pipeline SA (`VERTEX_PIPELINE_SERVICE_ACCOUNT`), customer-owned `VERTEX_AI_PIPELINE_ROOT`, resource labels (`GCP_CLIENT_LABEL`, `GCP_ENVIRONMENT`), and least-privilege IAM — see [ops/README.md](ops/README.md).

dbt models: `stg_vertex_model_predictions`, `stg_vertex_model_metadata`, `stg_vertex_job_runs` (sources in `dbt/models/sources/vertex.yml`). Apply DDL once: `vertex/ddl/vertex_bq_tables.sql` (`make vertex-bq-ddl` prints the path).

**Prefect** can run the same pipelines locally (sequential Docker steps) or submit a PipelineJob (`vertex_mode=vertex`). See [orchestration/README.md](../orchestration/README.md).

## Adding a model family

1. Add train / predict / optimize modules under `vertex/models/<family>/`.
2. Register runners in `models/registry.py` for `(model_type, step)`.
3. Add three config blocks to `model_config.yaml` (`job.step`, shared `model_family`).
4. Extend tests under `vertex/tests/`.

Planned: `prophet`.

## Troubleshooting

| Issue | Check |
|-------|--------|
| `Config with name '…' not found` | Config `name` in YAML matches `--config-name` / `VERTEX_*_CONFIG` |
| `No model artifacts` | Run train first; GCS path matches `inputs.gcs_model_path` and `artifact_config_name` |
| `VERTEX_AI_STAGING_BUCKET must be set` | `.env` or `vertex.staging_bucket` in config |
| `VERTEX_TRAINING_IMAGE` | Image exists in Artifact Registry and job SA can pull it |
| BigQuery load errors | Tables created from `ddl/vertex_bq_tables.sql`; SA has `bigquery.dataEditor` |
| Invalid JSON / empty credentials file | Set `GOOGLE_APPLICATION_CREDENTIALS_CONTAINER=/app/credentials/<same-basename-as-host>` in `.env` (see `env.example`) |

For environment variables shared with dbt and Docker Compose, see [env.example](../env.example) and the root README.
