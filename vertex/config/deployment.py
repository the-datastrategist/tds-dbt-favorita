"""Typed deployment manifest and resource catalog for portable environments."""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
PROJECT_PATTERN = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,1023}$")
REGION_PATTERN = re.compile(r"^[a-z]+-[a-z]+[0-9]$")
BUCKET_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]$")


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")
    return value


def _required(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    unresolved = ENV_PATTERN.findall(value)
    if unresolved:
        raise ValueError(f"{name} has unresolved environment variables: {', '.join(unresolved)}")
    return value.strip()


def _resolve(value: Any) -> Any:
    if isinstance(value, str):
        return ENV_PATTERN.sub(lambda match: os.environ.get(match.group(1), match.group(0)), value)
    if isinstance(value, list):
        return [_resolve(item) for item in value]
    if isinstance(value, dict):
        return {key: _resolve(item) for key, item in value.items()}
    return value


@dataclass(frozen=True)
class ResourceCatalog:
    """Validated cloud identifiers used to resolve tables and object paths."""

    platform_name: str
    environment: str
    project_id: str
    region: str
    bq_location: str
    raw_dataset: str
    platform_dataset: str
    model_bucket: str
    pipeline_bucket: str

    def table(self, relation: str, *, raw: bool = False) -> str:
        if not IDENTIFIER_PATTERN.fullmatch(relation):
            raise ValueError(f"invalid BigQuery relation: {relation!r}")
        dataset = self.raw_dataset if raw else self.platform_dataset
        return f"{self.project_id}.{dataset}.{relation}"

    def gcs_uri(self, kind: str, *parts: str) -> str:
        bucket = {"model": self.model_bucket, "pipeline": self.pipeline_bucket}.get(kind)
        if bucket is None:
            raise ValueError("kind must be 'model' or 'pipeline'")
        clean = [part.strip("/") for part in parts if part.strip("/")]
        return f"gs://{bucket}" + (f"/{'/'.join(clean)}" if clean else "")


def load_deployment(path: str | Path) -> ResourceCatalog:
    """Load a deployment manifest, resolve environment variables, and fail closed."""
    config_path = Path(path)
    with config_path.open(encoding="utf-8") as handle:
        root = _mapping(_resolve(yaml.safe_load(handle) or {}), "root")
    deployment = _mapping(root.get("deployment"), "deployment")
    cloud = _mapping(deployment.get("cloud"), "deployment.cloud")
    bigquery = _mapping(deployment.get("bigquery"), "deployment.bigquery")
    storage = _mapping(deployment.get("storage"), "deployment.storage")

    catalog = ResourceCatalog(
        platform_name=_required(deployment.get("platform_name"), "deployment.platform_name"),
        environment=_required(deployment.get("environment"), "deployment.environment"),
        project_id=_required(cloud.get("project_id"), "deployment.cloud.project_id"),
        region=_required(cloud.get("region"), "deployment.cloud.region"),
        bq_location=_required(bigquery.get("location"), "deployment.bigquery.location"),
        raw_dataset=_required(bigquery.get("raw_dataset"), "deployment.bigquery.raw_dataset"),
        platform_dataset=_required(
            bigquery.get("platform_dataset"), "deployment.bigquery.platform_dataset"
        ),
        model_bucket=_required(storage.get("model_bucket"), "deployment.storage.model_bucket"),
        pipeline_bucket=_required(
            storage.get("pipeline_bucket"), "deployment.storage.pipeline_bucket"
        ),
    )
    if not PROJECT_PATTERN.fullmatch(catalog.project_id):
        raise ValueError(f"invalid GCP project id: {catalog.project_id!r}")
    if not REGION_PATTERN.fullmatch(catalog.region):
        raise ValueError(f"invalid GCP region: {catalog.region!r}")
    for name, value in (
        ("raw_dataset", catalog.raw_dataset),
        ("platform_dataset", catalog.platform_dataset),
    ):
        if not IDENTIFIER_PATTERN.fullmatch(value):
            raise ValueError(f"invalid BigQuery {name}: {value!r}")
    for name, value in (
        ("model_bucket", catalog.model_bucket),
        ("pipeline_bucket", catalog.pipeline_bucket),
    ):
        if not BUCKET_PATTERN.fullmatch(value):
            raise ValueError(f"invalid GCS {name}: {value!r}")
    return catalog


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    try:
        catalog = load_deployment(args.config)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"Deployment validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    print(
        "Validated deployment "
        f"{catalog.platform_name}/{catalog.environment} in {catalog.project_id}."
    )


if __name__ == "__main__":
    main()
