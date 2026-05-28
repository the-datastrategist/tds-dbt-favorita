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

.PHONY: help install format lint test clean dbt-run dbt-train dbt-predict selector-daily-refresh selector-daily-refresh-test load-favorita-gcs load-favorita-bigquery

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
	poetry run black vertex tests
	poetry run isort vertex tests

lint: ## Lint code with flake8
	poetry run flake8 vertex tests

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
	docker compose run --rm ml-pipeline python scripts/load_favorita_to_gcs.py $(ARGS)

load-favorita-bigquery: ## Load Favorita 7z CSVs from GCS into BigQuery raw_favorita (Docker)
	docker compose run --rm ml-pipeline python scripts/load_favorita_to_bigquery.py $(ARGS)

# --- VERTEX MODEL COMMANDS ---

model-train: ## Train model using Vertex AI
	docker run --rm -v $(CURDIR):/app \
		-e GOOGLE_APPLICATION_CREDENTIALS=$(GOOGLE_APPLICATION_CREDENTIALS) \
		$(PROJECT_NAME) python -m $(VERTEX_DIR).models.sample_xgboost_train \
		--file_path $(VERTEX_DIR)/config/train_config.yaml

model-predict: ## Generate predictions using Vertex AI model
	docker run --rm -v $(CURDIR):/app \
		-e GOOGLE_APPLICATION_CREDENTIALS=$(GOOGLE_APPLICATION_CREDENTIALS) \
		$(PROJECT_NAME) python -m $(VERTEX_DIR).models.predict \
		--file_path $(VERTEX_DIR)/config/train_config.yaml

model-train-local: ## Train model locally (not in Docker)
	poetry run python -m $(VERTEX_DIR).models.sample_xgboost_train \
		--file_path $(VERTEX_DIR)/config/train_config.yaml

model-predict-local: ## Generate predictions locally (not in Docker)
	poetry run python -m $(VERTEX_DIR).models.predict \
		--file_path $(VERTEX_DIR)/config/train_config.yaml

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
