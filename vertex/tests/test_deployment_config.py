"""Tests for deployment/resource parameterization."""

from pathlib import Path

import pytest

from vertex.config.deployment import load_deployment


@pytest.mark.unit
def test_deployment_catalog_resolves_portable_resources(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TEST_PROJECT_ID", "client-forecast-prod")
    config = tmp_path / "deployment.yaml"
    config.write_text(
        """
deployment:
  platform_name: demand_forecasting
  environment: prod
  cloud:
    project_id: ${TEST_PROJECT_ID}
    region: us-east4
  bigquery:
    raw_dataset: source_raw
    platform_dataset: forecast_platform
    location: US
  storage:
    model_bucket: client-forecast-prod-models
    pipeline_bucket: client-forecast-prod-pipelines
""",
        encoding="utf-8",
    )

    catalog = load_deployment(config)

    assert catalog.table("forecast_outputs") == (
        "client-forecast-prod.forecast_platform.forecast_outputs"
    )
    assert catalog.table("sales", raw=True) == "client-forecast-prod.source_raw.sales"
    assert catalog.gcs_uri("model", "xgboost", "run-1") == (
        "gs://client-forecast-prod-models/xgboost/run-1"
    )


@pytest.mark.unit
def test_deployment_validation_rejects_unresolved_environment(tmp_path: Path):
    config = tmp_path / "deployment.yaml"
    config.write_text(
        Path("vertex/config/deployment.example.yaml")
        .read_text(encoding="utf-8")
        .replace("example-forecast-dev", "${MISSING_PROJECT_ID}", 1),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unresolved environment variables"):
        load_deployment(config)


@pytest.mark.unit
def test_resource_catalog_rejects_invalid_relation():
    catalog = load_deployment("vertex/config/deployment.example.yaml")

    with pytest.raises(ValueError, match="invalid BigQuery relation"):
        catalog.table("other-project.dataset.table")


@pytest.mark.unit
def test_catalog_exports_matching_dbt_and_terraform_values():
    catalog = load_deployment("vertex/config/deployment.example.yaml")

    assert catalog.dbt_environment() == {
        "GOOGLE_PROJECT_ID": "example-forecast-dev",
        "DBT_DATASET": "forecast_platform",
        "BQ_RAW_DATASET": "forecast_raw",
        "BQ_LOCATION": "US",
    }
    assert catalog.terraform_variables() == {
        "project_id": "example-forecast-dev",
        "region": "us-central1",
        "environment": "dev",
        "dbt_dataset": "forecast_platform",
        "raw_dataset": "forecast_raw",
    }
