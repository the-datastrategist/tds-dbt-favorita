# tds-favorita

Machine learning pipeline for Favorita sales forecasting using dbt (with BigQuery ML) and Google Vertex AI.

## Features

- **dbt + BigQuery ML**: Train and deploy ML models directly in BigQuery
- **Vertex AI**: Config-driven train / predict / optimize (XGBoost, Random Forest, ARIMA, SARIMA; Prophet planned), runnable in local Docker or as Vertex Custom Jobs
- **End-to-end Pipeline**: From data transformation to model training and prediction
- **Dockerized**: Run everything locally in Docker containers
- **Prefect**: OSS workflow orchestration for scheduled and manual dbt / Vertex / ML pipeline runs via Docker (`make prefect-*`; see [orchestration/README.md](orchestration/README.md))
- **Experiment tracking**: MLflow + Vertex AI Experiments on every Vertex job; GCS remains canonical for model files with MLflow catalog pointers on train (`make mlflow-ui`; see [Local UIs](#local-uis-mlflow--prefect))
- **pip + Docker**: Locked dependencies in `requirements.txt`; all local commands run in Docker
- **Testing**: pytest for Vertex utilities; dbt data tests on staging and intermediate models
- **CI/CD**: GitHub Actions on every push and PR (Python lint/tests, `dbt parse` / `dbt compile` / `dbt docs generate`)
- **Hosted dbt Docs**: GitHub Pages deploy on push to `main` / `master` (see [Hosted documentation](#hosted-documentation))
- **dbt Docs & lineage**: Project overview (`dbt/docs/overview.md`), exposures for ML and operational consumers (`dbt/models/exposures.yml`)
- **Code Quality**: Black, flake8, and mypy for code quality

## Project Structure

```
.
├── dbt/                    # dbt models and configurations
│   ├── docs/              # Project overview for dbt Docs (overview.md)
│   ├── models/
│   │   ├── staging/       # Staging models
│   │   ├── intermediate/  # ML training feature sets (int_sales_*)
│   │   ├── marts/         # Final models and BQML outputs
│   │   │   └── ml_models/ # BigQuery ML models
│   │   └── exposures.yml  # Downstream ML/dashboard lineage nodes
│   ├── macros/            # dbt macros for BigQuery ML
│   └── profiles/          # dbt profiles configuration
├── vertex/                # Vertex AI custom ML (see vertex/README.md)
│   ├── config/            # model_config.yaml + loader
│   ├── jobs/              # run.py (execute) and submit.py (Custom Jobs)
│   ├── models/            # xgboost/, sklearn/, timeseries/ + registry
│   ├── utils/             # BigQuery, GCS artifacts, predictions schema
│   ├── ddl/               # BigQuery table DDL for Vertex outputs
│   └── tests/             # pytest unit tests
├── orchestration/         # Prefect flows, tasks (see orchestration/README.md)
├── prefect.yaml           # Prefect deployment definitions
├── .github/workflows/     # CI and GitHub Pages (dbt docs)
├── Dockerfile             # Docker image definition
├── docker-compose.yml     # Docker Compose configuration
├── requirements.txt       # Locked Python dependencies (pip)
├── pyproject.toml         # Tool config (black, pytest, mypy)
└── Makefile               # Convenient commands

```

## Prerequisites

- Docker and Docker Compose
- Google Cloud Platform account with:
  - BigQuery dataset (`raw_favorita` for raw tables)
  - Vertex AI API enabled
  - Service account with appropriate permissions
  - GCS buckets: raw competition data (`.csv.7z`) and, for Vertex, model artifacts / staging (see `env.example`)
  - Vertex AI API enabled (if submitting Custom Jobs to GCP)

## Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd tds-favorita
   ```

2. **Set up environment variables**
   ```bash
   cp env.example .env
   # Edit .env with your Google Cloud credentials and configuration
   ```

3. **Set up Google Cloud credentials**
   ```bash
   mkdir -p credentials
   # Place your service account key JSON in credentials/ (gitignored)
   ```
   In `.env`, set both paths to the **same filename** (host path and container path):
   ```bash
   GOOGLE_APPLICATION_CREDENTIALS=./credentials/your-key.json
   GOOGLE_APPLICATION_CREDENTIALS_CONTAINER=/app/credentials/your-key.json
   ```
   The repo is bind-mounted at `/app`, so keys must live under `credentials/` — do not use an empty placeholder `service-account-key.json` unless that file contains valid JSON.

4. **Ensure raw data is in GCS**
   Place Favorita competition `.csv.7z` files in the bucket/prefix from `GCS_RAW_DATA_BUCKET` (see `env.example`). Download from the [Favorita competition](https://www.kaggle.com/competitions/favorita-grocery-sales-forecasting) if needed.

5. **Build the Docker image**
   ```bash
   make docker-build
   # or
   docker compose build
   ```

## Usage

Pipeline commands (dbt, data load, and the default Vertex train/predict targets) run in Docker via `make`. Pass extra CLI flags with `ARGS`, for example `make load-favorita-bigquery ARGS="--dry-run"`.

### Run from Docker (recommended)

Typical end-to-end flow:

```bash
# 1. Verify dbt can reach BigQuery
make dbt-debug

# 2. Install dbt packages
make dbt-deps

# 3. Load raw data from GCS into BigQuery (requires GCS_RAW_DATA_BUCKET in .env)
make load-favorita-bigquery

# 4. Run dbt models (staging → marts; excludes BQML unless selected)
make dbt-run

# 5. (Once) Create Vertex output tables in BigQuery — see vertex/ddl/vertex_bq_tables.sql

# 6. Train / predict / optimize with Vertex (runs in Docker by default)
make vertex-train
make vertex-predict
# make vertex-optimize   # optional Optuna search
```

For Vertex-specific setup, configs, and GCP submit: **[vertex/README.md](vertex/README.md)**.

For Prefect (scheduled / manual dbt, Vertex training, and ML pipelines): **[orchestration/README.md](orchestration/README.md)**.

Interactive shell inside the same image:

```bash
docker compose run --rm ml-pipeline bash
# then, e.g.: dbt run --project-dir dbt --target dev
```

List all `make` targets:

```bash
make help
```

### Data ingestion

Load [Favorita competition](https://www.kaggle.com/competitions/favorita-grocery-sales-forecasting) `.csv.7z` archives from GCS into BigQuery `raw_favorita` (tables used by dbt sources):

```bash
# Uses GCS_RAW_DATA_BUCKET, GOOGLE_PROJECT_ID, and BQ_RAW_DATASET from .env
make load-favorita-bigquery

# Preview without loading
make load-favorita-bigquery ARGS="--dry-run"

# Load a single table
make load-favorita-bigquery ARGS="--table raw_favorita_train"

# Override GCS source
make load-favorita-bigquery ARGS="--gcs-location gs://favorita-vertex-ai/source_data"
```

The service account needs read access to the GCS bucket and permission to load data into `tds-favorita.raw_favorita` (or your configured project/dataset).

### dbt commands (Docker)

```bash
make dbt-debug
make dbt-deps
make dbt-run
make dbt-train          # models tagged train (features + BQML training)
make dbt-predict        # models tagged predict
make dbt-test

# Single model
make dbt-run-model MODEL=int_sales_daily

# Extra dbt flags
make dbt-run ARGS="--select stg_favorita_train"

make dbt-docs-generate
make dbt-docs-serve     # http://localhost:8080
```

### dbt documentation and lineage

Narrative docs and exposures are configured in the dbt project (`docs-paths` in `dbt/dbt_project.yml`):

| File | Purpose |
|------|---------|
| [`dbt/docs/overview.md`](dbt/docs/overview.md) | **Overview** tab in dbt Docs: architecture, grains, run order, data-quality notes |
| [`dbt/models/exposures.yml`](dbt/models/exposures.yml) | Lineage **exposures** linking models to BQML forecasts, Vertex training, calendar/holiday context, and store master data |

Defined exposures include `favorita_company_forecast`, `favorita_store_product_features`, `favorita_vertex_training`, `favorita_operational_calendar`, and `favorita_store_master`. In the docs site, open the lineage graph and select an exposure to highlight upstream models.

Generate and browse docs locally (no `dbt run` required):

```bash
make dbt-docs-generate
make dbt-docs-serve     # http://localhost:8080 — open Overview, then explore Exposures in lineage
```

### Hosted documentation

After you enable **Settings → Pages → Build and deployment → GitHub Actions**, pushes to `main` / `master` run [`.github/workflows/docs.yml`](.github/workflows/docs.yml) and publish static dbt Docs.

**Public URL (replace org/repo with yours):**

`https://<github-org-or-user>.github.io/<repository-name>/`

The site includes the [project overview](dbt/docs/overview.md), model catalog, and [exposures](dbt/models/exposures.yml) on the lineage graph. No BigQuery credentials are required to browse it.

### Vertex AI model commands

Vertex jobs are defined in [`vertex/config/model_config.yaml`](vertex/config/model_config.yaml). Use **`VERTEX_MODE`** to choose where the job runs:

| `VERTEX_MODE` | Behavior |
|---------------|----------|
| `docker` (default) | Run `vertex.jobs.run` in the local Docker image |
| `vertex` | Submit a Vertex AI Custom Job (`vertex.jobs.submit`) |

```bash
# Local Docker (default)
make vertex-train
make vertex-predict
make vertex-optimize

# Vertex AI Custom Jobs (set VERTEX_AI_STAGING_BUCKET + VERTEX_TRAINING_IMAGE in .env)
make vertex-train VERTEX_MODE=vertex
make vertex-submit-train              # explicit submit
make vertex-train VERTEX_MODE=vertex SYNC=1   # submit and wait

```

**Vertex Pipelines** (KFP: optimize → train → predict) and **dbt staging** over Vertex BigQuery tables:

```bash
make vertex-pipeline-compile VERTEX_PIPELINE=favorita_xgboost
make vertex-pipeline-submit VERTEX_PIPELINE=favorita_xgboost VERTEX_MODE=vertex
make dbt-vertex    # stg_vertex_* models
```

Other useful targets:

```bash
make vertex-run-docker VERTEX_CONFIG_NAME=favorita_xgboost_train
make vertex-submit VERTEX_CONFIG_NAME=favorita_xgboost_predict
make help    # lists all vertex-* targets
```

Aliases: `make model-train` → `vertex-train-docker`, etc.

Full detail: **[vertex/README.md](vertex/README.md)**.

### Local UIs (MLflow & Prefect)

Both UIs run in Docker and bind to **localhost only** (override ports via Make variables):

| Command | URL | Purpose |
|---------|-----|---------|
| `make mlflow-ui` | http://127.0.0.1:5001 | Browse runs, metrics, and **Models** tab (GCS catalog pointers; not joblib copies) |
| `make prefect-ui` | http://127.0.0.1:4200 | Prefect OSS server (API + dashboard) |

```bash
# MLflow — runs until Ctrl+C; reads MLFLOW_TRACKING_URI from .env or file:/app/mlruns
make mlflow-ui

# Prefect — server in one terminal; worker in another to execute deployments
make prefect-ui
make prefect-work-pool-create   # once
make prefect-worker
```

Port **5001** is the default for MLflow because macOS **AirPlay Receiver** often occupies **5000**. Override if needed:

```bash
make mlflow-ui MLFLOW_UI_PORT=5002
make prefect-ui PREFECT_SERVER_PORT=4201
```

Prefect deployments, schedules, and flow triggers: **[orchestration/README.md](orchestration/README.md)**.

**MLflow catalog:** train jobs log `gcs_model_catalog.json` with `manifest_gcs_uri` / `joblib_gcs_uri`. Set `mlflow.register_model: true` in [`model_config.yaml`](vertex/config/model_config.yaml) or `MLFLOW_REGISTER_MODEL=true` to also create Model Registry versions. Predict still uses GCS via `make vertex-predict`. Details: **[vertex/README.md](vertex/README.md#experiment-tracking)**.

### Code Quality

```bash
# Format code
make format

# Lint code
make lint

# Type check
make type-check

# Run all checks
make check
```

### Testing

```bash
# Run all tests
make test

# Run with coverage
make test-cov

# Run only unit tests
make test-unit

# Run only integration tests
make test-integration

# dbt data tests (requires BigQuery credentials and built models)
make dbt-test
```

### Continuous integration

Pull requests and pushes to `main` / `master` run [`.github/workflows/ci.yml`](.github/workflows/ci.yml):

| Job | What it checks |
|-----|----------------|
| **python** | `flake8` on `vertex/`, then `pytest` |
| **dbt** | `dbt deps`, `dbt parse`, `dbt compile`, and `dbt docs generate` (no warehouse connection) |

Warehouse-backed checks (`dbt run`, `dbt test`) are run locally or in your GCP environment after `make dbt-debug`. To mirror CI checks in Docker:

```bash
make install
make lint
make test-unit
make dbt-deps
docker compose run --rm ml-pipeline dbt parse --project-dir dbt
docker compose run --rm ml-pipeline dbt compile --project-dir dbt
docker compose run --rm ml-pipeline dbt docs generate --project-dir dbt
```

To refresh locked dependencies after editing `requirements.in`:

```bash
make requirements-lock
```

## Machine Learning Workflows

### Option 1: BigQuery ML (SQL-based workflows)

1. **Load raw data to BigQuery** (from GCS `.csv.7z` archives)
   ```bash
   make load-favorita-bigquery
   ```

2. **Prepare training data with dbt**
   ```bash
   make dbt-run-model MODEL=int_sales_daily
   ```

3. **Train and run BQML models**
   ```bash
   make dbt-train
   make dbt-predict
   ```

### Option 2: Vertex AI (custom Python models)

Supported types: **xgboost**, **random_forest**, **arima**, **sarima** (see config names in [vertex/README.md](vertex/README.md#supported-model-types)).

1. **Create BigQuery output tables** (one time) — [`vertex/ddl/vertex_bq_tables.sql`](vertex/ddl/vertex_bq_tables.sql)

2. **Configure jobs** — [`vertex/config/model_config.yaml`](vertex/config/model_config.yaml)

3. **Prepare features in BigQuery** (if needed)
   ```bash
   make dbt-run-model MODEL=int_sales_store_daily
   ```

4. **Train, optimize (optional), predict**
   ```bash
   make docker-build
   make vertex-train                                    # XGBoost (default config)
   make vertex-train VERTEX_TRAIN_CONFIG=favorita_rf_train
   make vertex-optimize VERTEX_OPTIMIZE_CONFIG=favorita_arima_optimize
   make vertex-predict VERTEX_PREDICT_CONFIG=favorita_sarima_predict
   # Vertex AI Custom Jobs:
   make vertex-train VERTEX_MODE=vertex VERTEX_TRAIN_CONFIG=favorita_rf_train
   ```

See **[vertex/README.md](vertex/README.md)** for architecture, env vars, and troubleshooting.

## Environment Variables

Key environment variables (see `env.example` for full list):

- `GOOGLE_PROJECT_ID`: Your GCP project ID
- `GOOGLE_APPLICATION_CREDENTIALS`: Service account key on the host (e.g. `./credentials/your-key.json`)
- `GOOGLE_APPLICATION_CREDENTIALS_CONTAINER`: Same file inside Docker (e.g. `/app/credentials/your-key.json`); required for `make vertex-*` and dbt in the container
- `GCS_RAW_DATA_BUCKET`: GCS source for `.csv.7z` archives (`make load-favorita-bigquery`)
- `BQ_RAW_DATASET`: BigQuery dataset for raw tables (default: `raw_favorita`)
- `DBT_DATASET`: BigQuery dataset name for dbt models
- `VERTEX_AI_STAGING_BUCKET`: GCS prefix for Vertex Custom Job staging (required for `VERTEX_MODE=vertex`)
- `VERTEX_AI_MODEL_BUCKET`: GCS bucket for model artifacts (optional; paths also set in `model_config.yaml`)
- `VERTEX_TRAINING_IMAGE`: Container image URI for Custom Jobs (e.g. Artifact Registry `.../tds-favorita:latest`)
- `VERTEX_MODE` / `SYNC`: Make variables for Docker vs Vertex submit vs wait (see `make help`)
- `MLFLOW_TRACKING_URI`: Where Vertex jobs log experiments (default `file:./mlruns`; GCS optional)
- `MLFLOW_REGISTER_MODEL`: When `true`, register GCS catalog pointers in MLflow Model Registry on train
- `MLFLOW_UI_PORT`: Host port for `make mlflow-ui` (default `5001`)
- `PREFECT_SERVER_PORT`: Host port for `make prefect-ui` / `make prefect-server` (default `4200`)

## Development

All Python tooling runs inside the `ml-pipeline` container (`make docker-bash` for a shell), built on **Python 3.11** (`python:3.11-slim`). Update `requirements.in` / `requirements-dev.in`, then `make requirements-lock` and `make install` to rebuild the image.

### Adding New Models

1. **BigQuery ML**: Create new SQL model in `dbt/models/marts/ml_models/`
2. **Vertex AI**: Add modules under `vertex/models/<family>/`, register in `vertex/models/registry.py`, add train/predict/optimize blocks to `vertex/config/model_config.yaml` — see [vertex/README.md](vertex/README.md#adding-a-model-family)
3. **Lineage**: Add or update an exposure in `dbt/models/exposures.yml` when a new dashboard, app, or ML job consumes dbt models; refresh docs with `make dbt-docs-generate`

### Testing

Tests are located in `vertex/tests/` and `orchestration/tests/`. Run with:
```bash
make test
```

## What's Missing for End-to-End Predictions

To run end-to-end predictions from a local Dockerized environment, you'll need:

1. ✅ **Docker setup** - Complete
2. ✅ **dbt configuration** - Complete
3. ✅ **Vertex AI setup** - Config-driven jobs, Docker + Custom Job submit (see [vertex/README.md](vertex/README.md))
4. ✅ **Model training scripts** - XGBoost train / predict / optimize
5. ✅ **Prediction scripts** - Unified BigQuery prediction schema
6. ✅ **Prefect orchestration** - Manual and scheduled dbt, Vertex train, and ML pipeline (optimize → train → predict) deployments ([orchestration/README.md](orchestration/README.md))
   - Or use `make` commands for simple workflows
7. ✅ **Experiment tracking** - MLflow + Vertex AI Experiments; GCS-canonical artifacts with MLflow catalog on train (`gcs_model_catalog.json`; optional Model Registry via `MLFLOW_REGISTER_MODEL`)
   - ⚠️ Cloud Logging integration for Vertex AI (optional)
8. ⚠️ **Model serving** - For production:
   - Vertex AI Model Registry for model versioning
   - Vertex AI Endpoints for online predictions
   - Or BigQuery ML for batch predictions
9. ✅ **CI/CD** - GitHub Actions for lint, pytest, and dbt parse/compile/docs (see [Continuous integration](#continuous-integration))
10. ✅ **dbt Docs content** - Project overview and exposures (see [dbt documentation and lineage](#dbt-documentation-and-lineage))
11. ✅ **Hosted dbt Docs** - GitHub Pages via [docs.yml](.github/workflows/docs.yml) (enable Pages → GitHub Actions in repo settings)
12. ⚠️ **Warehouse CI** - Optional: add a protected workflow with GCP secrets for `dbt build` / `dbt test` on a dev dataset
13. ⚠️ **Automated retraining** - Scheduled jobs for model refresh (Composer, Cloud Run, or dbt Cloud)

## License

See LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests and linting: `make check && make test`
5. Submit a pull request