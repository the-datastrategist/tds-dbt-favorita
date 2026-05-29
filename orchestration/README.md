# Prefect orchestration

[Prefect](https://www.prefect.io/) (open source) schedules and runs the same workloads as the Makefile: **dbt run**, **Vertex train**, and full **ML pipelines** (optimize → train → predict) from `vertex/config/model_config.yaml`.

All commands run through **Docker** (`make` on the host, or direct `python`/`dbt` inside the `ml-pipeline` container). There is no host Poetry or pip workflow for Prefect.

Flow code lives under `orchestration/` (not `prefect/`) so it does not shadow the installed `prefect` Python package.

## Deployments

| Deployment | Flow | Purpose |
|------------|------|---------|
| `prefect-dbt-run-manual` | `prefect-dbt-run` | On-demand `make dbt-run` |
| `prefect-dbt-run-scheduled` | `prefect-dbt-run` | Daily `make dbt-run` (06:00 UTC) |
| `prefect-vertex-train-model-manual` | `prefect-vertex-train-model` | On-demand training |
| `prefect-vertex-train-model-schedule` | `prefect-vertex-train-model` | Daily training (07:00 UTC) |
| `prefect-vertex-ml-pipeline-manual` | `prefect-vertex-ml-pipeline` | On-demand ML pipeline (optimize → train → predict) |
| `prefect-vertex-ml-pipeline-scheduled` | `prefect-vertex-ml-pipeline` | Weekly XGBoost pipeline (Sunday 08:00 UTC) |

## Prerequisites

- Docker image built (`make install` or `make docker-build`)
- `.env` configured (same as the rest of the repo)
- For `vertex_mode=vertex`: Vertex AI staging bucket and training image in `.env`

## Local OSS setup (first time)

1. **Build the project image** (from repo root):

   ```bash
   make install
   ```

2. **Start the Prefect server** (API + UI at http://127.0.0.1:4200):

   ```bash
   make prefect-server
   ```

3. **Create a process work pool** (once per environment):

   ```bash
   make prefect-work-pool-create
   ```

4. **Register deployments** (in another terminal, with the server running):

   ```bash
   make prefect-deploy
   ```

5. **Start a worker** to execute flow runs (runs in Docker; talks to the server via `host.docker.internal`):

   ```bash
   make prefect-worker
   ```

6. **Trigger a deployment** (from the host):

   ```bash
   make prefect-run-dbt
   make prefect-run-vertex-train
   make prefect-run-vertex-train-all
   make prefect-run-vertex-pipeline
   make prefect-run-vertex-pipeline VERTEX_PIPELINE=favorita_arima
   ```

   Scheduled deployments run automatically when the worker is up and schedules are active.

## Flow parameters (Vertex train)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `config_name` | `favorita_xgboost_train` | Train config name from `model_config.yaml` |
| `train_all` | `false` | Train every non-legacy train config |
| `vertex_mode` | `docker` (or `PREFECT_DEFAULT_VERTEX_MODE`) | `docker` (in-container job) or `vertex` (Custom Job submit) |
| `sync` | `false` | With `vertex_mode=vertex`, wait for the Custom Job |

Train configs discovered for `train_all=true` (excluding legacy `train_*` aliases):

- `favorita_xgboost_train`
- `favorita_rf_train`
- `favorita_arima_train`
- `favorita_sarima_train`

## Flow parameters (ML pipeline)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `pipeline_name` | `favorita_xgboost` | Key under `pipelines:` in `model_config.yaml` |
| `vertex_mode` | `docker` | `docker`: sequential in-container steps; `vertex`: KFP PipelineJob |
| `sync` | `false` | With `vertex_mode=vertex`, wait for the PipelineJob |
| `skip_optimize` | `false` | Skip hyperparameter search |
| `skip_predict` | `false` | Skip scoring |

Pipelines (see [vertex/README.md](../vertex/README.md#pipelines-kfp-and-dbt-staging)):

| `pipeline_name` | Steps |
|-----------------|-------|
| `favorita_xgboost` | optimize, train, predict |
| `favorita_random_forest` | optimize, train, predict |
| `favorita_arima` | train, predict |

Submit a pipeline to Vertex AI from the host:

```bash
make vertex-pipeline-submit VERTEX_PIPELINE=favorita_xgboost SYNC=1
make vertex-pipeline-submit VERTEX_PIPELINE=favorita_xgboost SKIP_OPTIMIZE=1 SKIP_PREDICT=1
```

## Run flows without the server (development)

Runs the flow once inside Docker (no deployment registration required):

```bash
make prefect-flow-dbt
make prefect-flow-vertex-train
make prefect-flow-vertex-train VERTEX_TRAIN_CONFIG=favorita_rf_train VERTEX_MODE=vertex SYNC=1
make prefect-flow-vertex-pipeline
make prefect-flow-vertex-pipeline VERTEX_PIPELINE=favorita_arima SKIP_OPTIMIZE=1 SKIP_PREDICT=1
```

## How tasks relate to Make

The Prefect **worker** runs inside `ml-pipeline`. Flow tasks call `python -m vertex.jobs.*` and `dbt` directly (same as what `make vertex-run-docker` and `make dbt-run` run via Docker on the host). They do not spawn nested `docker compose` processes.

| Host | In-container (Prefect worker) |
|------|-------------------------------|
| `make dbt-run` | `dbt run --project-dir dbt ...` |
| `make vertex-run-docker` | `python -m vertex.jobs.run ...` |
| `make vertex-submit` | `python -m vertex.jobs.submit ...` |
| `make vertex-pipeline-submit` | `python -m vertex.jobs.submit_pipeline ...` |

## Layout

```
orchestration/
  flows/          # @flow definitions (dbt, vertex train, vertex ML pipeline)
  tasks/          # @task implementations (in-container python/dbt)
  utils/          # repo root, .env, train + pipeline config resolution
prefect.yaml      # deployment definitions (repo root)
```

## Environment variables

Optional entries in `.env` (see `env.example`):

- `PREFECT_API_URL` — API URL for workers/deploy (default in Makefile: `http://host.docker.internal:4200/api`)
- `PREFECT_SERVER_PORT` — host port for `make prefect-server` (default `4200`)
- `PREFECT_DEFAULT_VERTEX_MODE` — default `vertex_mode` for Vertex flows (`docker` or `vertex`)

Scheduled cron expressions are defined in `prefect.yaml`; edit there to change times or timezones.
