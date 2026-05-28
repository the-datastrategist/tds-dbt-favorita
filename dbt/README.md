# tds-favorita

Machine learning pipeline for Favorita sales forecasting using dbt (with BigQuery ML) and Google Vertex AI.

## Features

- **dbt + BigQuery ML**: Train and deploy ML models directly in BigQuery
- **Vertex AI**: Train custom models (XGBoost, etc.) and deploy to Vertex AI
- **End-to-end Pipeline**: From data transformation to model training and prediction
- **Dockerized**: Run everything locally in Docker containers
- **Poetry**: Modern Python dependency management
- **Testing**: pytest for Vertex utilities; dbt data tests on staging and intermediate models
- **CI/CD**: GitHub Actions on every push and PR (Python lint/tests, `dbt parse` / `dbt compile`)
- **Code Quality**: Black, flake8, and mypy for code quality

## Project Structure

```
.
├── dbt/                    # dbt models and configurations
│   ├── models/
│   │   ├── staging/       # Staging models
│   │   ├── intermediate/  # ML training feature sets (int_train_input_*)
│   │   └── marts/         # Final models and BQML outputs
│   │       └── ml_models/ # BigQuery ML models
│   ├── macros/            # dbt macros for BigQuery ML
│   └── profiles/          # dbt profiles configuration
├── vertex/                # Vertex AI model code
│   ├── models/            # Training and prediction scripts
│   ├── utils/             # Utilities (data loading, Vertex helpers)
│   └── config/            # Model configuration files
├── tests/                 # Python test suite (pytest)
├── .github/workflows/     # CI (lint, pytest, dbt parse/compile)
├── Dockerfile             # Docker image definition
├── docker-compose.yml     # Docker Compose configuration
├── pyproject.toml         # Poetry dependencies
└── Makefile               # Convenient commands

```

## Prerequisites

- Docker and Docker Compose
- Google Cloud Platform account with:
  - BigQuery dataset (`raw_favorita` for raw tables)
  - Vertex AI API enabled
  - Service account with appropriate permissions
  - GCS bucket with Favorita competition archives (`.csv.7z`), e.g. `gs://favorita-vertex-ai/source_data`

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
   # Place your service account key JSON in credentials/ and set GOOGLE_APPLICATION_CREDENTIALS in .env
   # Example: GOOGLE_APPLICATION_CREDENTIALS=./credentials/tds-favorita-xxxxxxxxxx.json
   ```
   Ensure `docker-compose.yml` mounts that file at the path used by `GOOGLE_APPLICATION_CREDENTIALS` inside the container (see the `ml-pipeline` service `volumes` section).

4. **Ensure raw data is in GCS**
   Place Favorita competition `.csv.7z` files in the bucket/prefix from `GCS_RAW_DATA_BUCKET` (see `env.example`). Download from the [Favorita competition](https://www.kaggle.com/competitions/favorita-grocery-sales-forecasting) if needed.

5. **Build the Docker image**
   ```bash
   make docker-build
   # or
   docker compose build
   ```

6. **Install dependencies locally (optional, for development without Docker)**
   ```bash
   poetry install
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

# 5. Train / predict with Vertex scripts (runs in Docker)
make model-train
make model-predict
```

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
make dbt-run-model MODEL=int_train_input_daily

# Extra dbt flags
make dbt-run ARGS="--select stg_favorita_train"

make dbt-docs-generate
make dbt-docs-serve     # http://localhost:8080
```

### Vertex AI model commands

Default targets run in Docker (`docker run` with the project image):

```bash
make model-train
make model-predict
```

Optional local runs (Poetry on the host, no Docker):

```bash
make model-train-local
make model-predict-local
```

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

Pull requests and pushes to `main` / `master` run [`.github/workflows/ci.yml`](../.github/workflows/ci.yml):

| Job | What it checks |
|-----|----------------|
| **python** | `flake8` on `vertex/` and `tests/`, then `pytest` |
| **dbt** | `dbt deps`, `dbt parse`, and `dbt compile` (no warehouse connection) |

Warehouse-backed checks (`dbt run`, `dbt test`) are run locally or in your GCP environment after `make dbt-debug`. To mirror CI locally without Docker:

```bash
poetry install
export GOOGLE_PROJECT_ID=ci-placeholder DBT_DATASET=favorita DBT_PROFILES_DIR=dbt/profiles
echo '{}' > /tmp/ci-service-account.json
export GOOGLE_APPLICATION_CREDENTIALS=/tmp/ci-service-account.json
poetry run flake8 vertex tests
poetry run pytest
poetry run dbt deps --project-dir dbt
poetry run dbt parse --project-dir dbt
poetry run dbt compile --project-dir dbt
```

## Machine Learning Workflows

### Option 1: BigQuery ML (SQL-based workflows)

1. **Load raw data to BigQuery** (from GCS `.csv.7z` archives)
   ```bash
   make load-favorita-bigquery
   ```

2. **Prepare training data with dbt**
   ```bash
   make dbt-run-model MODEL=int_train_input_daily
   ```

3. **Train and run BQML models**
   ```bash
   make dbt-train
   make dbt-predict
   ```

### Option 2: Vertex AI (custom XGBoost models)

1. **Configure training** — edit `vertex/config/train_config.yaml`

2. **Prepare features in BigQuery** (if needed)
   ```bash
   make dbt-run-model MODEL=int_train_input_daily
   ```

3. **Train and predict**
   ```bash
   make model-train
   make model-predict
   ```

## Environment Variables

Key environment variables (see `env.example` for full list):

- `GOOGLE_PROJECT_ID`: Your GCP project ID
- `GOOGLE_APPLICATION_CREDENTIALS`: Path to service account key JSON (host path; must match a `docker-compose.yml` volume mount)
- `GCS_RAW_DATA_BUCKET`: GCS source for `.csv.7z` archives (`make load-favorita-bigquery`)
- `BQ_RAW_DATASET`: BigQuery dataset for raw tables (default: `raw_favorita`)
- `DBT_DATASET`: BigQuery dataset name for dbt models
- `VERTEX_AI_MODEL_BUCKET`: GCS bucket for model artifacts

## Development

### Local development (without Docker)

1. Install Poetry: https://python-poetry.org/docs/#installation
2. Install dependencies: `poetry install`
3. Set up environment variables in `.env`
4. Run tools directly, for example:
   ```bash
   poetry run python scripts/load_favorita_to_bigquery.py
   poetry run dbt run --project-dir dbt
   make model-train-local
   ```

### Adding New Models

1. **BigQuery ML**: Create new SQL model in `dbt/models/marts/ml_models/`
2. **Vertex AI**: Create new training script in `vertex/models/` and config in `vertex/config/`

### Testing

Tests are located in `tests/`. Run with:
```bash
poetry run pytest
```

## What's Missing for End-to-End Predictions

To run end-to-end predictions from a local Dockerized environment, you'll need:

1. ✅ **Docker setup** - Complete
2. ✅ **dbt configuration** - Complete
3. ✅ **Vertex AI setup** - Complete
4. ✅ **Model training scripts** - Complete
5. ✅ **Prediction scripts** - Complete
6. ⚠️ **Data pipeline orchestration** - Consider adding:
   - Airflow or Prefect for workflow orchestration
   - Or use `make` commands for simple workflows
7. ⚠️ **Monitoring and logging** - Consider adding:
   - MLflow or Weights & Biases for experiment tracking
   - Cloud Logging integration for Vertex AI
8. ⚠️ **Model serving** - For production:
   - Vertex AI Model Registry for model versioning
   - Vertex AI Endpoints for online predictions
   - Or BigQuery ML for batch predictions
9. ✅ **CI/CD** - GitHub Actions for lint, pytest, and dbt parse/compile (see [Continuous integration](#continuous-integration))
10. ⚠️ **Warehouse CI** - Optional: add a protected workflow with GCP secrets for `dbt build` / `dbt test` on a dev dataset
11. ⚠️ **Automated retraining** - Scheduled jobs for model refresh (Composer, Cloud Run, or dbt Cloud)

## License

See LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests and linting: `make check && make test`
5. Submit a pull request
