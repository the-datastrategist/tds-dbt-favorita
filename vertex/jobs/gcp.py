"""
GCP / Vertex AI settings shared by Custom Jobs and Pipeline Jobs.

Consulting template defaults: explicit env vars, optional YAML overrides, resource
labels for cost allocation, and a dedicated pipeline service account when provided.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class GcpSettings:
    """Resolved GCP project, region, buckets, and container for Vertex workloads."""

    project_id: str
    region: str
    staging_bucket: str
    pipeline_root: str
    training_image: str
    machine_type: str
    service_account: Optional[str] = None
    network: Optional[str] = None
    labels: dict[str, str] = field(default_factory=dict)
    experiment: Optional[str] = None


def _require(value: Optional[str], name: str) -> str:
    if not value:
        raise EnvironmentError(f"{name} must be set")
    return value


def _normalize_bucket(uri: str) -> str:
    return uri if uri.startswith("gs://") else f"gs://{uri}"


def standard_labels(
    *,
    config: dict[str, Any],
    step: Optional[str] = None,
    managed_by: str = "vertex-jobs",
) -> dict[str, str]:
    """Build GCP resource labels (values must be lowercase)."""
    spec_job = (config.get("job") or {}) if config else {}
    labels = {
        "managed_by": _label_value(managed_by),
        "model_family": _label_value(config.get("model_family") or "unknown"),
        "model_type": _label_value(spec_job.get("model_type") or "unknown"),
    }
    if step:
        labels["job_step"] = _label_value(step)
    env_label = os.getenv("GCP_ENVIRONMENT") or os.getenv("DBT_TARGET") or "dev"
    labels["environment"] = _label_value(env_label)
    client = os.getenv("GCP_CLIENT_LABEL") or os.getenv("CLIENT_NAME")
    if client:
        labels["client"] = _label_value(client)
    extra = (config.get("vertex") or {}).get("labels") or {}
    if isinstance(extra, dict):
        for key, value in extra.items():
            labels[_label_value(key)] = _label_value(str(value))
    return labels


def _label_value(raw: str) -> str:
    """Sanitize to GCP label value charset."""
    cleaned = raw.lower().replace(" ", "-").replace("_", "-")
    return cleaned[:63]


def resolve_gcp_settings(
    config: Optional[dict[str, Any]] = None,
    *,
    image_uri: Optional[str] = None,
) -> GcpSettings:
    """Merge environment variables with optional per-config vertex: block."""
    inputs = (config or {}).get("inputs") or {}
    vertex_cfg = (config or {}).get("vertex") or {}

    project_id = (
        inputs.get("project_id")
        or os.getenv("VERTEX_AI_PROJECT_ID")
        or os.getenv("GOOGLE_PROJECT_ID")
    )
    project_id = _require(project_id, "GOOGLE_PROJECT_ID")

    region = (
        inputs.get("region")
        or os.getenv("VERTEX_AI_REGION")
        or os.getenv("GOOGLE_REGION")
        or "us-central1"
    )

    staging_bucket = _normalize_bucket(
        _require(
            vertex_cfg.get("staging_bucket") or os.getenv("VERTEX_AI_STAGING_BUCKET"),
            "VERTEX_AI_STAGING_BUCKET",
        )
    )

    pipeline_root = vertex_cfg.get("pipeline_root") or os.getenv("VERTEX_AI_PIPELINE_ROOT")
    if not pipeline_root:
        pipeline_root = f"{staging_bucket.rstrip('/')}/pipeline-root"
    pipeline_root = _normalize_bucket(pipeline_root)

    training_image = image_uri or vertex_cfg.get("image") or os.getenv("VERTEX_TRAINING_IMAGE")
    training_image = _require(
        training_image,
        "VERTEX_TRAINING_IMAGE",
    )

    machine_type = vertex_cfg.get("machine_type", "n1-standard-4")
    service_account = vertex_cfg.get("service_account") or os.getenv(
        "VERTEX_PIPELINE_SERVICE_ACCOUNT"
    )
    network = vertex_cfg.get("network") or os.getenv("VERTEX_NETWORK")

    labels = standard_labels(config=config or {}, managed_by="vertex-jobs")
    experiment = vertex_cfg.get("experiment")

    return GcpSettings(
        project_id=project_id,
        region=region,
        staging_bucket=staging_bucket,
        pipeline_root=pipeline_root,
        training_image=training_image,
        machine_type=machine_type,
        service_account=service_account,
        network=network,
        labels=labels,
        experiment=experiment,
    )


def worker_pool_spec(
    settings: GcpSettings,
    *,
    config_name: str,
    config_path: str,
    job_run_id: str,
    command: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    """Custom Job worker pool spec running vertex.jobs.run for one config."""
    run_command = command or ["python", "-m", "vertex.jobs.run"]
    env = [
        {"name": "GOOGLE_PROJECT_ID", "value": settings.project_id},
        {"name": "VERTEX_JOB_RUN_ID", "value": job_run_id},
        {"name": "VERTEX_AI_REGION", "value": settings.region},
    ]
    creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if creds:
        env.append({"name": "GOOGLE_APPLICATION_CREDENTIALS", "value": creds})

    return [
        {
            "machine_spec": {"machine_type": settings.machine_type},
            "replica_count": 1,
            "container_spec": {
                "image_uri": settings.training_image,
                "command": run_command,
                "args": [
                    "--config-path",
                    config_path,
                    "--config-name",
                    config_name,
                ],
                "env": env,
            },
        }
    ]
