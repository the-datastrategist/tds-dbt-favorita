# Makefile for tds-favorita ML pipeline

.DEFAULT_GOAL := help
PROJECT_NAME = tds-favorita
DBT_DIR = dbt
VERTEX_DIR = vertex

# Load .env variables
ifneq ("$(wildcard .env)","")
	include .env
	export $(shell sed 's/=.*//' .env)
endif

.PHONY: help install format lint test clean dbt-run dbt-train dbt-predict selector-daily-refresh selector-daily-refresh-test load-favorita-gcs load-favorita-bigquery \
	vertex-train vertex-predict vertex-optimize vertex-run vertex-run-docker vertex-run-local vertex-submit vertex-submit-local \
	vertex-train-docker vertex-predict-docker vertex-optimize-docker \
	vertex-train-local vertex-predict-local vertex-optimize-local \
	vertex-submit-train vertex-submit-predict vertex-submit-optimize \
	vertex-pipeline-compile vertex-pipeline-submit vertex-pipeline-submit-sync \
	dbt-vertex vertex-bq-ddl \
	model-train model-predict model-optimize model-train-local model-predict-local model-optimize-local \
	vertex-submit-train docker-build

help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# --- SETUP COMMANDS ---

install: ## Install dependencies with Poetry
	poetry install

install-no-dev: ## Install dependencies without dev dependencies
	poetry install --no-dev

update: ## Update dependencies
	poetry update

lock: ## Lock dependencies
	poetry lock

# --- CODE QUALITY COMMANDS ---

format: ## Format code with black and isort
	poetry run black vertex
	poetry run isort vertex

lint: ## Lint code with flake8
	poetry run flake8 vertex

type-check: ## Type check with mypy
	poetry run mypy vertex

check: format lint type-check ## Run all code quality checks

# --- TESTING COMMANDS ---

test: ## Run tests with pytest
	poetry run pytest

test-cov: ## Run tests with coverage report
	poetry run pytest --cov=vertex --cov-report=html --cov-report=term

test-unit: ## Run only unit tests
	poetry run pytest -m unit

test-integration: ## Run only integration tests
	poetry run pytest -m integration

# --- DOCKER COMMANDS ---

docker-build: ## Build Docker image
	docker build -t $(PROJECT_NAME):latest .

docker-bash: ## Start interactive bash shell in Docker
	docker run --rm -it -v $(CURDIR):/app \
		-e GOOGLE_APPLICATION_CREDENTIALS=$(GOOGLE_APPLICATION_CREDENTIALS) \
		$(PROJECT_NAME) bash

docker-run: ## Run default command in Docker
	docker run --rm -v $(CURDIR):/app \
		-e GOOGLE_APPLICATION_CREDENTIALS=$(GOOGLE_APPLICATION_CREDENTIALS) \
		$(PROJECT_NAME)


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

load-favorita-gcs: ## Download Kaggle Favorita data and upload to GCS (Docker)
	docker compose run --rm ml-pipeline python $(ARGS)

load-favorita-bigquery: ## Load Favorita 7z CSVs from GCS into BigQuery raw_favorita (Docker)
	docker compose run --rm ml-pipeline python scripts/load_favorita_to_bigquery.py $(ARGS)

# --- VERTEX MODEL COMMANDS ---
# Run locally in Docker:  make vertex-train  (default VERTEX_MODE=docker)
# Run on Vertex AI:      make vertex-train VERTEX_MODE=vertex
# Run via Poetry on host: make vertex-train VERTEX_MODE=local
#
# Override config:       make vertex-predict VERTEX_CONFIG_NAME=my_predict_config
# Wait for Vertex job:   make vertex-train VERTEX_MODE=vertex SYNC=1
# Requires: docker-build, .env with GOOGLE_PROJECT_ID; for Vertex also
#   VERTEX_AI_STAGING_BUCKET and VERTEX_TRAINING_IMAGE (or vertex.* in YAML).

VERTEX_CONFIG = $(VERTEX_DIR)/config/model_config.yaml
VERTEX_TRAIN_CONFIG ?= favorita_xgboost_train
VERTEX_PREDICT_CONFIG ?= favorita_xgboost_predict
VERTEX_OPTIMIZE_CONFIG ?= favorita_xgboost_optimize
VERTEX_PIPELINE ?= favorita_xgboost
VERTEX_CONFIG_NAME ?=
VERTEX_MODE ?= docker
# Set SYNC=1 to block until a submitted Custom Job finishes
SYNC ?=

# Host path to GCP credentials (relative to repo root or absolute)
GOOGLE_CREDS_HOST ?= credentials/tds-favorita-b72f306edf29.json
GOOGLE_CREDS_CONTAINER = /app/$(GOOGLE_CREDS_HOST)
VERTEX_SUBMIT_SYNC_FLAG = $(if $(filter 1 true yes,$(SYNC)),--sync,)

# Shared Docker run for Vertex jobs (mounts repo + credentials)
DOCKER_VERTEX = docker run --rm \
	-v $(CURDIR):/app \
	-w /app \
	-e PYTHONPATH=/app \
	-e GOOGLE_PROJECT_ID=$(GOOGLE_PROJECT_ID) \
	-e GOOGLE_APPLICATION_CREDENTIALS=$(GOOGLE_CREDS_CONTAINER) \
	-e VERTEX_AI_PROJECT_ID=$(VERTEX_AI_PROJECT_ID) \
	-e VERTEX_AI_REGION=$(VERTEX_AI_REGION) \
	-e VERTEX_AI_STAGING_BUCKET=$(VERTEX_AI_STAGING_BUCKET) \
	-e VERTEX_AI_MODEL_BUCKET=$(VERTEX_AI_MODEL_BUCKET) \
	-e VERTEX_TRAINING_IMAGE=$(VERTEX_TRAINING_IMAGE) \
	-v $(CURDIR)/$(GOOGLE_CREDS_HOST):$(GOOGLE_CREDS_CONTAINER):ro \
	$(PROJECT_NAME)

# --- Generic runners (set VERTEX_CONFIG_NAME) ---

vertex-run-docker: ## Run a config in Docker (VERTEX_CONFIG_NAME=...)
	@test -n "$(VERTEX_CONFIG_NAME)" || (echo "Set VERTEX_CONFIG_NAME, e.g. make vertex-run-docker VERTEX_CONFIG_NAME=favorita_xgboost_train" && exit 1)
	$(DOCKER_VERTEX) python -m $(VERTEX_DIR).jobs.run \
		--config-path $(VERTEX_CONFIG) \
		--config-name $(VERTEX_CONFIG_NAME)

vertex-run-local: ## Run a config via Poetry on the host (VERTEX_CONFIG_NAME=...)
	@test -n "$(VERTEX_CONFIG_NAME)" || (echo "Set VERTEX_CONFIG_NAME" && exit 1)
	poetry run python -m $(VERTEX_DIR).jobs.run \
		--config-path $(VERTEX_CONFIG) \
		--config-name $(VERTEX_CONFIG_NAME)

vertex-submit: ## Submit a config to Vertex AI Custom Training (VERTEX_CONFIG_NAME=...)
	@test -n "$(VERTEX_CONFIG_NAME)" || (echo "Set VERTEX_CONFIG_NAME" && exit 1)
	$(DOCKER_VERTEX) python -m $(VERTEX_DIR).jobs.submit \
		--config-path $(VERTEX_CONFIG) \
		--config-name $(VERTEX_CONFIG_NAME) \
		$(VERTEX_SUBMIT_SYNC_FLAG)

vertex-submit-local: ## Submit to Vertex AI using Poetry on the host (VERTEX_CONFIG_NAME=...)
	@test -n "$(VERTEX_CONFIG_NAME)" || (echo "Set VERTEX_CONFIG_NAME" && exit 1)
	poetry run python -m $(VERTEX_DIR).jobs.submit \
		--config-path $(VERTEX_CONFIG) \
		--config-name $(VERTEX_CONFIG_NAME) \
		$(VERTEX_SUBMIT_SYNC_FLAG)

# Dispatch by VERTEX_MODE (docker | local | vertex)
vertex-run: ## Run or submit VERTEX_CONFIG_NAME (VERTEX_MODE=docker|local|vertex)
	@test -n "$(VERTEX_CONFIG_NAME)" || (echo "Set VERTEX_CONFIG_NAME" && exit 1)
	@case "$(VERTEX_MODE)" in \
		local) $(MAKE) vertex-run-local VERTEX_CONFIG_NAME="$(VERTEX_CONFIG_NAME)" ;; \
		vertex) $(MAKE) vertex-submit VERTEX_CONFIG_NAME="$(VERTEX_CONFIG_NAME)" SYNC="$(SYNC)" ;; \
		*) $(MAKE) vertex-run-docker VERTEX_CONFIG_NAME="$(VERTEX_CONFIG_NAME)" ;; \
	esac

# --- Train / predict / optimize (pick VERTEX_MODE) ---

vertex-train: ## Train (VERTEX_MODE=docker|local|vertex, default docker)
	@$(MAKE) vertex-run VERTEX_CONFIG_NAME=$(VERTEX_TRAIN_CONFIG) VERTEX_MODE=$(VERTEX_MODE) SYNC=$(SYNC)

vertex-predict: ## Predict (VERTEX_MODE=docker|local|vertex)
	@$(MAKE) vertex-run VERTEX_CONFIG_NAME=$(VERTEX_PREDICT_CONFIG) VERTEX_MODE=$(VERTEX_MODE) SYNC=$(SYNC)

vertex-optimize: ## Hyperparameter search (VERTEX_MODE=docker|local|vertex)
	@$(MAKE) vertex-run VERTEX_CONFIG_NAME=$(VERTEX_OPTIMIZE_CONFIG) VERTEX_MODE=$(VERTEX_MODE) SYNC=$(SYNC)

# --- Explicit Docker targets ---

vertex-train-docker: ## Train in Docker
	@$(MAKE) vertex-run-docker VERTEX_CONFIG_NAME=$(VERTEX_TRAIN_CONFIG)

vertex-predict-docker: ## Predict in Docker
	@$(MAKE) vertex-run-docker VERTEX_CONFIG_NAME=$(VERTEX_PREDICT_CONFIG)

vertex-optimize-docker: ## Optimize in Docker
	@$(MAKE) vertex-run-docker VERTEX_CONFIG_NAME=$(VERTEX_OPTIMIZE_CONFIG)

# --- Explicit local (Poetry) targets ---

vertex-train-local: ## Train via Poetry on host
	@$(MAKE) vertex-run-local VERTEX_CONFIG_NAME=$(VERTEX_TRAIN_CONFIG)

vertex-predict-local: ## Predict via Poetry on host
	@$(MAKE) vertex-run-local VERTEX_CONFIG_NAME=$(VERTEX_PREDICT_CONFIG)

vertex-optimize-local: ## Optimize via Poetry on host
	@$(MAKE) vertex-run-local VERTEX_CONFIG_NAME=$(VERTEX_OPTIMIZE_CONFIG)

# --- Explicit Vertex AI submit targets ---

vertex-submit-train: ## Submit training Custom Job to Vertex AI
	@$(MAKE) vertex-submit VERTEX_CONFIG_NAME=$(VERTEX_TRAIN_CONFIG) SYNC=$(SYNC)

vertex-submit-predict: ## Submit prediction Custom Job to Vertex AI
	@$(MAKE) vertex-submit VERTEX_CONFIG_NAME=$(VERTEX_PREDICT_CONFIG) SYNC=$(SYNC)

vertex-submit-optimize: ## Submit optimization Custom Job to Vertex AI
	@$(MAKE) vertex-submit VERTEX_CONFIG_NAME=$(VERTEX_OPTIMIZE_CONFIG) SYNC=$(SYNC)

# --- Vertex Pipelines (KFP) ---

vertex-pipeline-compile: ## Compile KFP JSON (VERTEX_PIPELINE=favorita_xgboost)
	$(DOCKER_VERTEX) python -m $(VERTEX_DIR).pipelines.compile \
		--pipeline $(VERTEX_PIPELINE) \
		--config-path $(VERTEX_CONFIG)

vertex-pipeline-submit: ## Submit Vertex PipelineJob (optimize→train→predict)
	$(DOCKER_VERTEX) python -m $(VERTEX_DIR).jobs.submit_pipeline \
		--pipeline $(VERTEX_PIPELINE) \
		--config-path $(VERTEX_CONFIG) \
		$(VERTEX_SUBMIT_SYNC_FLAG)

vertex-pipeline-submit-sync: ## Submit pipeline and wait until complete
	@$(MAKE) vertex-pipeline-submit SYNC=1

vertex-pipeline-train-only: ## Pipeline without optimize/predict steps
	$(DOCKER_VERTEX) python -m $(VERTEX_DIR).jobs.submit_pipeline \
		--pipeline $(VERTEX_PIPELINE) \
		--config-path $(VERTEX_CONFIG) \
		--skip-optimize --skip-predict \
		$(VERTEX_SUBMIT_SYNC_FLAG)

# --- dbt + BigQuery ops ---

dbt-vertex: ## Build staging views over Vertex output tables
	docker compose run --rm ml-pipeline dbt run --project-dir dbt --target $(DBT_TARGET) --select tag:vertex $(ARGS)

vertex-bq-ddl: ## Print path to BigQuery DDL for Vertex tables
	@echo "Apply with bq query: $(VERTEX_DIR)/ddl/vertex_bq_tables.sql"

# --- Backward-compatible aliases ---

model-train: vertex-train-docker ## Alias: train in Docker
model-predict: vertex-predict-docker ## Alias: predict in Docker
model-optimize: vertex-optimize-docker ## Alias: optimize in Docker
model-train-local: vertex-train-local ## Alias: train via Poetry
model-predict-local: vertex-predict-local ## Alias: predict via Poetry
model-optimize-local: vertex-optimize-local ## Alias: optimize via Poetry

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

clean-all: clean ## Clean all including Poetry cache
	poetry cache clear pypi --all .
