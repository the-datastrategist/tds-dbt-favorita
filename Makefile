# Makefile for tds-favorita ML pipeline

.DEFAULT_GOAL := help
PROJECT_NAME = tds-favorita
DBT_DIR = dbt
VERTEX_DIR = vertex
DOCKER_RUN = docker compose run --rm ml-pipeline

# Load .env variables
ifneq ("$(wildcard .env)","")
	include .env
	export $(shell sed 's/=.*//' .env)
endif
# Docker ml-pipeline uses GOOGLE_APPLICATION_CREDENTIALS_CONTAINER (see docker-compose.yml).
ifeq ($(GOOGLE_APPLICATION_CREDENTIALS_CONTAINER),)
ifneq ($(GOOGLE_APPLICATION_CREDENTIALS),)
GOOGLE_APPLICATION_CREDENTIALS_CONTAINER := /app/$(patsubst ./%,%,$(GOOGLE_APPLICATION_CREDENTIALS))
export GOOGLE_APPLICATION_CREDENTIALS_CONTAINER
endif
endif

.PHONY: help install requirements-lock format lint test clean dbt-run dbt-train dbt-predict selector-daily-refresh selector-daily-refresh-test load-favorita-gcs load-favorita-bigquery \
	mlflow-ui prefect-ui prefect-server prefect-work-pool-create prefect-worker prefect-deploy \
	prefect-run-dbt prefect-run-vertex-train prefect-run-vertex-train-all prefect-run-vertex-pipeline \
	prefect-flow-dbt prefect-flow-vertex-train prefect-flow-vertex-pipeline \
	vertex-train vertex-predict vertex-optimize vertex-run vertex-run-docker vertex-submit \
	vertex-train-docker vertex-predict-docker vertex-optimize-docker \
	vertex-submit-train vertex-submit-predict vertex-submit-optimize \
	vertex-pipeline-compile vertex-pipeline-submit vertex-pipeline-submit-sync \
	dbt-vertex vertex-bq-ddl vertex-validate-config vertex-validate-configs \
	model-train model-predict model-optimize docker-build docker-bash

help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# --- SETUP COMMANDS ---

install: docker-build ## Build Docker image (installs Python deps from requirements-dev.txt)

requirements-lock: ## Regenerate requirements.txt and requirements-dev.txt (requires Docker)
	docker run --rm -v $(CURDIR):/work -w /work python:3.11-slim bash -c '\
		pip install -q pip-tools && \
		pip-compile requirements.in -o requirements.txt --strip-extras && \
		pip-compile requirements-dev.in -o requirements-dev.txt --strip-extras'

# --- CODE QUALITY COMMANDS ---

format: ## Format code with black and isort
	$(DOCKER_RUN) black vertex orchestration
	$(DOCKER_RUN) isort vertex orchestration

lint: ## Lint code with flake8
	$(DOCKER_RUN) flake8 vertex orchestration

type-check: ## Type check with mypy
	$(DOCKER_RUN) mypy vertex orchestration

check: format lint type-check ## Run all code quality checks

# --- TESTING COMMANDS ---

test: ## Run tests with pytest
	$(DOCKER_RUN) pytest

test-cov: ## Run tests with coverage report
	$(DOCKER_RUN) pytest --cov=vertex --cov-report=html --cov-report=term

test-unit: ## Run only unit tests
	$(DOCKER_RUN) pytest -m unit

test-integration: ## Run only integration tests
	$(DOCKER_RUN) pytest -m integration

# --- DOCKER COMMANDS ---

docker-build: ## Build Docker image
	docker compose build

docker-bash: ## Start interactive bash shell in Docker
	docker compose run --rm -it ml-pipeline bash


# DBT COMMANDS

# Standard dbt run - excludes BQML models
dbt-run:
	docker compose run --rm ml-pipeline dbt run --project-dir dbt --target $(DBT_TARGET) --exclude tag:bqml $(ARGS)

# Daily ETL: staging + intermediate features (see dbt/selectors.yml)
selector-daily-refresh: ## Run dbt with selector daily_refresh (staging + features, no BQML)
	docker compose run --rm ml-pipeline dbt run --project-dir dbt --target $(DBT_TARGET) --selector daily_refresh $(ARGS)

selector-daily-refresh-test: ## Run data tests for daily_refresh + singular data_quality tests (no BQML)
	docker compose run --rm ml-pipeline dbt test --project-dir dbt --target $(DBT_TARGET) --selector daily_refresh_tests $(ARGS)

# Run all dbt models used for training (features + BQML training)
dbt-train:
	docker compose run --rm ml-pipeline dbt run --project-dir dbt --target $(DBT_TARGET) --select tag:train $(ARGS)

# Run all dbt models used for prediction, evaluation, and explanation
dbt-predict:
	docker compose run --rm ml-pipeline dbt run --project-dir dbt --target $(DBT_TARGET) --select tag:predict $(ARGS)

dbt-run-full-refresh:
	docker compose run --rm ml-pipeline dbt run --project-dir dbt --target $(DBT_TARGET) --full-refresh --exclude tag:bqml $(ARGS)

dbt-run-model:
	docker compose run --rm ml-pipeline dbt run --project-dir dbt --target $(DBT_TARGET) --select $(MODEL) $(ARGS)

dbt-run-operation:
	docker compose run --rm ml-pipeline dbt run-operation --project-dir dbt $(MODEL) --target $(DBT_TARGET) $(ARGS)

dbt-deps:
	docker compose run --rm ml-pipeline dbt deps --project-dir dbt $(ARGS)

dbt-test:
	docker compose run --rm ml-pipeline dbt test --project-dir dbt --target $(DBT_TARGET) $(ARGS)

dbt-debug:
	docker compose run --rm ml-pipeline dbt debug --project-dir dbt --target $(DBT_TARGET) $(ARGS)

dbt-seed:
	docker compose run --rm ml-pipeline dbt seed --project-dir dbt --target $(DBT_TARGET) $(ARGS)

dbt-create-table:
	docker compose run --rm ml-pipeline dbt run-operation --project-dir dbt stage_external_sources --args '{"select": "$(DATABASE).$(TABLE)"}' --target $(DBT_TARGET)

dbt-docs:
	docker compose run --rm ml-pipeline dbt docs generate --project-dir dbt && docker compose run --rm -p 8080:8080 ml-pipeline dbt docs serve --project-dir dbt --host 0.0.0.0 --port 8080

dbt-docs-generate:
	docker compose run --rm ml-pipeline dbt docs generate --project-dir dbt

dbt-docs-serve:
	docker compose run --rm -p 8080:8080 ml-pipeline dbt docs serve --project-dir dbt --host 0.0.0.0 --port 8080

# --- DATA INGESTION ---

load-favorita-gcs: ## Download Kaggle Favorita data and upload to GCS (Docker; pass script via ARGS)
	$(DOCKER_RUN) python $(ARGS)

load-favorita-bigquery: ## Load Favorita 7z CSVs from GCS into BigQuery raw_favorita (Docker)
	docker compose run --rm ml-pipeline python scripts/load_favorita_to_bigquery.py $(ARGS)

# --- VERTEX MODEL COMMANDS ---
# Run in Docker:         make vertex-train  (default VERTEX_MODE=docker)
# Run on Vertex AI:      make vertex-train VERTEX_MODE=vertex
#
# Override config:       make vertex-predict VERTEX_CONFIG_NAME=my_predict_config
# Wait for Vertex job:   make vertex-train VERTEX_MODE=vertex SYNC=1
# Requires: make install, .env with GOOGLE_PROJECT_ID; for Vertex also
#   VERTEX_AI_STAGING_BUCKET and VERTEX_TRAINING_IMAGE (or vertex.* in YAML).

VERTEX_CONFIG = $(VERTEX_DIR)/config/model_config.yaml
VERTEX_TRAIN_CONFIG ?=
VERTEX_PREDICT_CONFIG ?= favorita_xgboost
VERTEX_OPTIMIZE_CONFIG ?= favorita_xgboost
VERTEX_PIPELINE ?= favorita_xgboost
VERTEX_CONFIG_NAME ?=
VERTEX_STEP ?=
VERTEX_MODE ?= docker
# Set SYNC=1 to block until a submitted Custom Job finishes
SYNC ?=

VERTEX_SUBMIT_SYNC_FLAG = $(if $(filter 1 true yes,$(SYNC)),--sync,)
VERTEX_STEP_FLAG = $(if $(VERTEX_STEP),--step $(VERTEX_STEP),)

# --- Generic runners (set VERTEX_CONFIG_NAME) ---

vertex-run-docker: ## Run a config in Docker (VERTEX_CONFIG_NAME=..., optional VERTEX_STEP=)
	@test -n "$(VERTEX_CONFIG_NAME)" || (echo "Set VERTEX_CONFIG_NAME, e.g. make vertex-run-docker VERTEX_CONFIG_NAME=favorita_xgboost" && exit 1)
	$(DOCKER_RUN) python -m $(VERTEX_DIR).jobs.run \
		--config-path $(VERTEX_CONFIG) \
		--config-name $(VERTEX_CONFIG_NAME) \
		$(VERTEX_STEP_FLAG)

vertex-submit: ## Submit a config to Vertex AI Custom Training (VERTEX_CONFIG_NAME=..., VERTEX_STEP=)
	@test -n "$(VERTEX_CONFIG_NAME)" || (echo "Set VERTEX_CONFIG_NAME" && exit 1)
	$(DOCKER_RUN) python -m $(VERTEX_DIR).jobs.submit \
		--config-path $(VERTEX_CONFIG) \
		--config-name $(VERTEX_CONFIG_NAME) \
		$(VERTEX_STEP_FLAG) \
		$(VERTEX_SUBMIT_SYNC_FLAG)

# Dispatch by VERTEX_MODE (docker | vertex)
vertex-run: ## Run or submit VERTEX_CONFIG_NAME (VERTEX_MODE=docker|vertex)
	@test -n "$(VERTEX_CONFIG_NAME)" || (echo "Set VERTEX_CONFIG_NAME" && exit 1)
	@case "$(VERTEX_MODE)" in \
		vertex) $(MAKE) vertex-submit VERTEX_CONFIG_NAME="$(VERTEX_CONFIG_NAME)" SYNC="$(SYNC)" ;; \
		*) $(MAKE) vertex-run-docker VERTEX_CONFIG_NAME="$(VERTEX_CONFIG_NAME)" ;; \
	esac

# --- Train / predict / optimize (pick VERTEX_MODE) ---

vertex-train: ## Train all include_in_run configs, or one if VERTEX_CONFIG_NAME / VERTEX_TRAIN_CONFIG set
	@if [ -n "$(VERTEX_CONFIG_NAME)" ] || [ -n "$(VERTEX_TRAIN_CONFIG)" ]; then \
		$(MAKE) vertex-run VERTEX_CONFIG_NAME="$(or $(VERTEX_CONFIG_NAME),$(VERTEX_TRAIN_CONFIG))" VERTEX_MODE=$(VERTEX_MODE) SYNC=$(SYNC); \
	else \
		$(DOCKER_RUN) python -m $(VERTEX_DIR).jobs.run_batch \
			--step train \
			--config-path $(VERTEX_CONFIG) \
			$(if $(filter vertex,$(VERTEX_MODE)),--vertex-mode vertex,) \
			$(VERTEX_SUBMIT_SYNC_FLAG); \
	fi

vertex-predict: ## Predict (VERTEX_MODE=docker|vertex; VERTEX_PREDICT_CONFIG, VERTEX_STEP=predict)
	@$(MAKE) vertex-run VERTEX_CONFIG_NAME=$(VERTEX_PREDICT_CONFIG) VERTEX_STEP=predict VERTEX_MODE=$(VERTEX_MODE) SYNC=$(SYNC)

vertex-optimize: ## Hyperparameter search (VERTEX_OPTIMIZE_CONFIG, VERTEX_STEP=optimize)
	@$(MAKE) vertex-run VERTEX_CONFIG_NAME=$(VERTEX_OPTIMIZE_CONFIG) VERTEX_STEP=optimize VERTEX_MODE=$(VERTEX_MODE) SYNC=$(SYNC)

# --- Explicit Docker targets ---

vertex-train-docker: ## Train in Docker (all include_in_run when VERTEX_TRAIN_CONFIG unset)
	@if [ -n "$(VERTEX_TRAIN_CONFIG)" ]; then \
		$(MAKE) vertex-run-docker VERTEX_CONFIG_NAME=$(VERTEX_TRAIN_CONFIG); \
	else \
		$(DOCKER_RUN) python -m $(VERTEX_DIR).jobs.run_batch \
			--step train \
			--config-path $(VERTEX_CONFIG); \
	fi

vertex-predict-docker: ## Predict in Docker
	@$(MAKE) vertex-run-docker VERTEX_CONFIG_NAME=$(VERTEX_PREDICT_CONFIG) VERTEX_STEP=predict

vertex-optimize-docker: ## Optimize in Docker
	@$(MAKE) vertex-run-docker VERTEX_CONFIG_NAME=$(VERTEX_OPTIMIZE_CONFIG) VERTEX_STEP=optimize

# --- Explicit Vertex AI submit targets ---

vertex-submit-train: ## Submit training Custom Job(s) to Vertex AI
	@if [ -n "$(VERTEX_TRAIN_CONFIG)" ]; then \
		$(MAKE) vertex-submit VERTEX_CONFIG_NAME=$(VERTEX_TRAIN_CONFIG) SYNC=$(SYNC); \
	else \
		$(DOCKER_RUN) python -m $(VERTEX_DIR).jobs.run_batch \
			--step train \
			--config-path $(VERTEX_CONFIG) \
			--vertex-mode vertex \
			$(VERTEX_SUBMIT_SYNC_FLAG); \
	fi

vertex-submit-predict: ## Submit prediction Custom Job to Vertex AI
	@$(MAKE) vertex-submit VERTEX_CONFIG_NAME=$(VERTEX_PREDICT_CONFIG) VERTEX_STEP=predict SYNC=$(SYNC)

vertex-submit-optimize: ## Submit optimization Custom Job to Vertex AI
	@$(MAKE) vertex-submit VERTEX_CONFIG_NAME=$(VERTEX_OPTIMIZE_CONFIG) VERTEX_STEP=optimize SYNC=$(SYNC)

# --- Vertex Pipelines (KFP) ---

vertex-pipeline-compile: ## Compile KFP JSON (VERTEX_PIPELINE=favorita_xgboost)
	$(DOCKER_RUN) python -m $(VERTEX_DIR).pipelines.compile \
		--pipeline $(VERTEX_PIPELINE) \
		--config-path $(VERTEX_CONFIG)

VERTEX_PIPELINE_SKIP_OPTIMIZE_FLAG = $(if $(filter 1 true yes,$(SKIP_OPTIMIZE)),--skip-optimize,)
VERTEX_PIPELINE_SKIP_PREDICT_FLAG = $(if $(filter 1 true yes,$(SKIP_PREDICT)),--skip-predict,)

vertex-pipeline-submit: ## Submit Vertex PipelineJob (optimize→train→predict)
	$(DOCKER_RUN) python -m $(VERTEX_DIR).jobs.submit_pipeline \
		--pipeline $(VERTEX_PIPELINE) \
		--config-path $(VERTEX_CONFIG) \
		$(VERTEX_SUBMIT_SYNC_FLAG) \
		$(VERTEX_PIPELINE_SKIP_OPTIMIZE_FLAG) \
		$(VERTEX_PIPELINE_SKIP_PREDICT_FLAG)

vertex-pipeline-submit-sync: ## Submit pipeline and wait until complete
	@$(MAKE) vertex-pipeline-submit SYNC=1

vertex-pipeline-train-only: ## Pipeline without optimize/predict steps
	$(DOCKER_RUN) python -m $(VERTEX_DIR).jobs.submit_pipeline \
		--pipeline $(VERTEX_PIPELINE) \
		--config-path $(VERTEX_CONFIG) \
		--skip-optimize --skip-predict \
		$(VERTEX_SUBMIT_SYNC_FLAG)

# --- dbt + BigQuery ops ---

dbt-vertex: ## Build staging views over Vertex output tables
	docker compose run --rm ml-pipeline dbt run --project-dir dbt --target $(DBT_TARGET) --select tag:vertex $(ARGS)

vertex-bq-ddl: ## Create BigQuery tables for Vertex ML outputs (once per environment)
	docker compose run --rm ml-pipeline python scripts/apply_vertex_bq_ddl.py

vertex-validate-config: ## Validate a model config (MODEL=favorita_xgboost)
	@test -n "$(MODEL)" || (echo "Set MODEL, e.g. make vertex-validate-config MODEL=favorita_xgboost" && exit 1)
	$(DOCKER_RUN) python -c "\
from vertex.config.load_config import load_model_config, validate_config_all_steps; \
c = load_model_config('$(MODEL)'); \
validate_config_all_steps(c); \
print('OK')"

vertex-validate-configs: ## Validate all model configs in model_config.yaml
	$(DOCKER_RUN) python -m $(VERTEX_DIR).config.validate_all

# --- Backward-compatible aliases ---

model-train: vertex-train-docker ## Alias: train in Docker
model-predict: vertex-predict-docker ## Alias: predict in Docker
model-optimize: vertex-optimize-docker ## Alias: optimize in Docker

# --- MLflow / Prefect UIs (localhost only; override ports via MLFLOW_UI_PORT / PREFECT_SERVER_PORT) ---
# Train jobs log gcs_model_catalog.json to MLflow; set MLFLOW_REGISTER_MODEL=true for Model Registry.

MLFLOW_UI_PORT ?= 5001
MLFLOW_TRACKING_URI ?= file:/app/mlruns

mlflow-ui: ## MLflow tracking UI (http://127.0.0.1:5001; avoids macOS AirPlay on 5000)
	docker compose run --rm -p 127.0.0.1:$(MLFLOW_UI_PORT):5000 ml-pipeline \
		mlflow ui --host 0.0.0.0 --backend-store-uri $(MLFLOW_TRACKING_URI)

# --- PREFECT COMMANDS ---

PREFECT_SERVER_PORT ?= 4200
PREFECT_API_URL_DOCKER ?= http://host.docker.internal:$(PREFECT_SERVER_PORT)/api

prefect-server: ## Start Prefect OSS server (UI http://127.0.0.1:4200; localhost only)
	docker compose run --rm -p 127.0.0.1:$(PREFECT_SERVER_PORT):4200 ml-pipeline prefect server start --host 0.0.0.0

prefect-ui: prefect-server ## Alias: Prefect OSS UI (http://127.0.0.1:4200)

prefect-work-pool-create: ## Create default process work pool (idempotent)
	$(DOCKER_RUN) prefect work-pool create --type process default 2>/dev/null || true

prefect-worker: ## Start worker for the default work pool (server must be running)
	docker compose run --rm -e PREFECT_API_URL=$(PREFECT_API_URL_DOCKER) ml-pipeline prefect worker start --pool default

prefect-deploy: ## Register all deployments from prefect.yaml
	docker compose run --rm -e PREFECT_API_URL=$(PREFECT_API_URL_DOCKER) ml-pipeline prefect deploy --all

# Trigger deployments (Prefect server + worker must be running)
prefect-run-dbt: ## Trigger manual prefect-dbt-run deployment
	$(DOCKER_RUN) -e PREFECT_API_URL=$(PREFECT_API_URL_DOCKER) prefect deployment run 'prefect-dbt-run/prefect-dbt-run-manual'

prefect-run-vertex-train: ## Trigger manual Vertex train deployment (VERTEX_TRAIN_CONFIG)
	$(DOCKER_RUN) -e PREFECT_API_URL=$(PREFECT_API_URL_DOCKER) prefect deployment run \
		'prefect-vertex-train-model/prefect-vertex-train-model-manual' \
		--param config_name=$(VERTEX_TRAIN_CONFIG)

prefect-run-vertex-train-all: ## Trigger Vertex train-all deployment
	$(DOCKER_RUN) -e PREFECT_API_URL=$(PREFECT_API_URL_DOCKER) prefect deployment run \
		'prefect-vertex-train-model/prefect-vertex-train-model-manual' \
		--param train_all=true --param config_name=null

prefect-run-vertex-pipeline: ## Trigger manual ML pipeline deployment (VERTEX_PIPELINE)
	$(DOCKER_RUN) -e PREFECT_API_URL=$(PREFECT_API_URL_DOCKER) prefect deployment run \
		'prefect-vertex-ml-pipeline/prefect-vertex-ml-pipeline-manual' \
		--param pipeline_name=$(VERTEX_PIPELINE)

# Run flows directly in Docker (no Prefect server; for development)
prefect-flow-dbt: ## Run prefect-dbt-run flow once in Docker
	$(DOCKER_RUN) python -c "from orchestration.flows.dbt import prefect_dbt_run_flow; prefect_dbt_run_flow()"

prefect-flow-vertex-train: ## Run prefect-vertex-train flow once (VERTEX_TRAIN_CONFIG, VERTEX_MODE)
	$(DOCKER_RUN) python -c "\
from orchestration.flows.vertex import prefect_vertex_train_model_flow; \
prefect_vertex_train_model_flow(config_name='$(VERTEX_TRAIN_CONFIG)', vertex_mode='$(VERTEX_MODE)', sync=$(if $(filter 1 true yes,$(SYNC)),True,False))"

prefect-flow-vertex-pipeline: ## Run prefect-vertex-ml-pipeline flow once (VERTEX_PIPELINE, VERTEX_MODE)
	$(DOCKER_RUN) python -c "\
from orchestration.flows.vertex_pipeline import prefect_vertex_ml_pipeline_flow; \
prefect_vertex_ml_pipeline_flow(\
pipeline_name='$(VERTEX_PIPELINE)', vertex_mode='$(VERTEX_MODE)', sync=$(if $(filter 1 true yes,$(SYNC)),True,False), \
skip_optimize=$(if $(filter 1 true yes,$(SKIP_OPTIMIZE)),True,False), skip_predict=$(if $(filter 1 true yes,$(SKIP_PREDICT)),True,False))"

# --- CLEANUP COMMANDS ---

clean: ## Clean generated files and artifacts
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	rm -rf htmlcov
	rm -rf .coverage
	rm -rf $(DBT_DIR)/target
	rm -rf $(DBT_DIR)/dbt_packages
	rm -rf $(VERTEX_DIR)/models/tmp
	find . -type d -name __pycache__ -exec rm -r {} +
	find . -type f -name "*.pyc" -delete

clean-all: clean ## Clean generated artifacts (same as clean)
	@true
