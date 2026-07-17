"""Tests for GcpSettings resolution and Custom Job worker pool spec construction."""

import pytest

from vertex.jobs.gcp import resolve_gcp_settings, worker_pool_spec


@pytest.fixture
def gcp_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_PROJECT_ID", "test-project")
    monkeypatch.setenv("VERTEX_AI_STAGING_BUCKET", "gs://test-bucket")
    monkeypatch.setenv("VERTEX_TRAINING_IMAGE", "us-central1-docker.pkg.dev/test/test:latest")
    monkeypatch.setenv(
        "VERTEX_PIPELINE_SERVICE_ACCOUNT", "sa-vertex-ml@test-project.iam.gserviceaccount.com"
    )


@pytest.mark.unit
class TestWorkerPoolSpec:
    def test_env_never_contains_google_application_credentials(self, gcp_env, monkeypatch):
        # A local key-file path should never leak into the Custom Job's container env — Custom
        # Jobs authenticate via their attached service_account + ADC, not a key file. See
        # docs/specs/workload_identity_federation.md.
        monkeypatch.setenv(
            "GOOGLE_APPLICATION_CREDENTIALS", "/app/credentials/service-account-key.json"
        )
        settings = resolve_gcp_settings({})
        spec = worker_pool_spec(
            settings,
            config_name="favorita_store_n1d_xgboost",
            config_path="vertex/config/model_config.yaml",
            job_run_id="job-123",
        )
        env_names = {var["name"] for var in spec[0]["container_spec"]["env"]}
        assert "GOOGLE_APPLICATION_CREDENTIALS" not in env_names

    def test_env_contains_expected_vars(self, gcp_env):
        settings = resolve_gcp_settings({})
        spec = worker_pool_spec(
            settings,
            config_name="favorita_store_n1d_xgboost",
            config_path="vertex/config/model_config.yaml",
            job_run_id="job-123",
        )
        env = {var["name"]: var["value"] for var in spec[0]["container_spec"]["env"]}
        assert env == {
            "GOOGLE_PROJECT_ID": "test-project",
            "VERTEX_JOB_RUN_ID": "job-123",
            "VERTEX_AI_REGION": "us-central1",
        }

    def test_service_account_carried_on_settings_not_env(self, gcp_env):
        # The Custom Job authenticates as settings.service_account via the request's
        # service_account field (set in vertex/jobs/submit.py), not via an env var.
        settings = resolve_gcp_settings({})
        assert settings.service_account == "sa-vertex-ml@test-project.iam.gserviceaccount.com"
