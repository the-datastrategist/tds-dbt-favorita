"""GCS artifact layout and manifest helpers for Vertex training."""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from datetime import datetime as dt
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import joblib
from google.cloud import storage

logger = logging.getLogger(__name__)

VERTEX_SKLEARN_SERVING_IMAGE = "us-docker.pkg.dev/vertex-ai/prediction/sklearn-cpu.0-24:latest"


def parse_gcs_uri(gcs_uri: str) -> tuple[str, str]:
    if not gcs_uri.startswith("gs://"):
        raise ValueError(f"Expected gs:// URI, got: {gcs_uri}")
    parsed = urlparse(gcs_uri)
    bucket = parsed.netloc
    prefix = parsed.path.lstrip("/")
    return bucket, prefix


def vertex_model_dir() -> Optional[Path]:
    raw = os.getenv("AIP_MODEL_DIR")
    if not raw:
        return None
    path = Path(raw)
    path.mkdir(parents=True, exist_ok=True)
    return path


def build_manifest(
    *,
    config_name: str,
    model_type: str,
    model_run_id: str,
    model_id: str,
    model_family: Optional[str],
    target_column: str,
    features: list[str],
    parameters: dict[str, Any],
    model_file: str = "model.json",
    joblib_file: str = "model.joblib",
    gcs_prefix: Optional[str] = None,
) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "config_name": config_name,
        "model_family": model_family,
        "model_type": model_type,
        "model_run_id": model_run_id,
        "model_id": model_id,
        "target_column": target_column,
        "features": features,
        "parameters": parameters,
        "model_file": model_file,
        "joblib_file": joblib_file,
        "sklearn_serving_image": VERTEX_SKLEARN_SERVING_IMAGE,
    }
    if gcs_prefix:
        manifest["gcs_prefix"] = gcs_prefix
    return manifest


def upload_bytes(
    bucket: storage.Bucket,
    blob_path: str,
    payload: bytes,
    content_type: str,
) -> str:
    bucket.blob(blob_path).upload_from_string(payload, content_type=content_type)
    return f"gs://{bucket.name}/{blob_path}"


def upload_manifest(
    bucket: storage.Bucket,
    blob_path: str,
    manifest: dict[str, Any],
) -> str:
    return upload_bytes(
        bucket,
        blob_path,
        json.dumps(manifest, default=str).encode("utf-8"),
        content_type="application/json",
    )


def artifact_prefix(
    gcs_model_path: str,
    config_name: str,
    model_type: str,
    run_at: Optional[dt] = None,
) -> str:
    run_time = (run_at or dt.utcnow()).strftime("%Y%m%dT%H%M%S")
    bucket_name, base_prefix = parse_gcs_uri(gcs_model_path)
    if base_prefix and not base_prefix.endswith("/"):
        base_prefix = f"{base_prefix}/"
    prefix = f"{base_prefix}{config_name}/{model_type}_{config_name}_{run_time}"
    return f"gs://{bucket_name}/{prefix}"


def _entry_from_manifest(
    bucket_name: str,
    prefix: str,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    model_file = manifest.get("model_file", "model.json")
    model_uri = f"gs://{bucket_name}/{prefix}/{model_file}"
    return {
        "prefix": prefix,
        "artifact_uri": model_uri,
        "model_json_uri": model_uri if model_file.endswith(".json") else None,
        "manifest_uri": f"gs://{bucket_name}/{prefix}/manifest.json",
        "model_run_id": manifest.get("model_run_id"),
        "manifest": manifest,
        "sort_key": prefix,
    }


def list_model_artifacts(
    gcs_model_path: str,
    artifact_config_name: str,
    *,
    model_run_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    """
    List trained model directories under artifact_config_name, newest first.

    Discovers runs via manifest.json (supports joblib-only and XGBoost json bundles).
    """
    bucket_name, base_prefix = parse_gcs_uri(gcs_model_path)
    if base_prefix and not base_prefix.endswith("/"):
        base_prefix = f"{base_prefix}/"
    search_prefix = f"{base_prefix}{artifact_config_name}/"

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    seen_prefixes: set[str] = set()
    entries: list[dict[str, Any]] = []

    for blob in bucket.list_blobs(prefix=search_prefix):
        if not blob.name.endswith("/manifest.json"):
            continue
        prefix = blob.name.rsplit("/", 1)[0]
        if prefix in seen_prefixes:
            continue
        seen_prefixes.add(prefix)
        manifest = json.loads(bucket.blob(blob.name).download_as_text())
        entry_run_id = manifest.get("model_run_id")
        if model_run_id and entry_run_id != model_run_id:
            continue
        entries.append(_entry_from_manifest(bucket_name, prefix, manifest))

    # Legacy layouts without manifest: index model.json blobs
    if not entries:
        for blob in bucket.list_blobs(prefix=search_prefix):
            if not blob.name.endswith("/model.json"):
                continue
            prefix = blob.name.rsplit("/", 1)[0]
            if prefix in seen_prefixes:
                continue
            seen_prefixes.add(prefix)
            manifest_path = f"{prefix}/manifest.json"
            manifest: dict[str, Any] = {}
            if bucket.blob(manifest_path).exists():
                manifest = json.loads(bucket.blob(manifest_path).download_as_text())
            entry_run_id = manifest.get("model_run_id")
            if model_run_id and entry_run_id != model_run_id:
                continue
            if manifest:
                entries.append(_entry_from_manifest(bucket_name, prefix, manifest))
            else:
                entries.append(
                    {
                        "prefix": prefix,
                        "artifact_uri": f"gs://{bucket_name}/{blob.name}",
                        "model_json_uri": f"gs://{bucket_name}/{blob.name}",
                        "manifest_uri": f"gs://{bucket_name}/{manifest_path}",
                        "model_run_id": entry_run_id,
                        "manifest": manifest,
                        "sort_key": prefix,
                    }
                )

    entries.sort(key=lambda item: item["sort_key"], reverse=True)
    return entries


def resolve_latest_artifact(
    gcs_model_path: str,
    artifact_config_name: Optional[str] = None,
    *,
    model_run_id: Optional[str] = None,
) -> tuple[str, dict[str, Any]]:
    """Return (model_json_uri, manifest) for the latest or pinned training run."""
    if artifact_config_name:
        entries = list_model_artifacts(
            gcs_model_path,
            artifact_config_name,
            model_run_id=model_run_id,
        )
    else:
        bucket_name, base_prefix = parse_gcs_uri(gcs_model_path)
        if base_prefix and not base_prefix.endswith("/"):
            base_prefix = f"{base_prefix}/"
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        entries = []
        for blob in bucket.list_blobs(prefix=base_prefix):
            if not blob.name.endswith("/manifest.json"):
                continue
            manifest = json.loads(bucket.blob(blob.name).download_as_text())
            if model_run_id and manifest.get("model_run_id") != model_run_id:
                continue
            prefix = blob.name.rsplit("/", 1)[0]
            entries.append(_entry_from_manifest(bucket_name, prefix, manifest))
        entries.sort(key=lambda item: item["sort_key"], reverse=True)

    if not entries:
        raise FileNotFoundError(
            f"No model artifacts (artifact_config_name={artifact_config_name!r}, "
            f"model_run_id={model_run_id!r})"
        )
    chosen = entries[0]
    manifest = chosen.get("manifest") or {}
    if not manifest and chosen.get("manifest_uri"):
        bucket_name, blob_path = parse_gcs_uri(chosen["manifest_uri"])
        client = storage.Client()
        raw = client.bucket(bucket_name).blob(blob_path).download_as_text()
        manifest = json.loads(raw)
    artifact_uri = chosen.get("artifact_uri") or chosen.get("model_json_uri")
    return artifact_uri, manifest


def load_joblib_from_gcs(gcs_uri: str) -> Any:
    """Load a joblib-serialized object from GCS."""
    import io

    if not gcs_uri.startswith("gs://"):
        raise ValueError(f"Expected gs:// URI, got: {gcs_uri}")
    bucket_name, blob_path = parse_gcs_uri(gcs_uri)
    client = storage.Client()
    payload = client.bucket(bucket_name).blob(blob_path).download_as_bytes()
    return joblib.load(io.BytesIO(payload))


def save_joblib_artifacts(
    model: Any,
    *,
    model_run_id: str,
    model_id: str,
    config_name: str,
    model_family: Optional[str],
    model_type: str,
    target_column: str,
    parameters: dict[str, Any],
    gcs_model_path: str,
    features: Optional[list[str]] = None,
    run_at: Optional[dt] = None,
    extra_manifest: Optional[dict[str, Any]] = None,
) -> tuple[str, str]:
    """
    Persist joblib model + manifest to GCS.

    Returns:
        (joblib_gcs_uri, manifest_gcs_uri)
    """
    run_at = run_at or dt.utcnow()
    prefix_uri = artifact_prefix(gcs_model_path, config_name, model_type, run_at)
    bucket_name, prefix = parse_gcs_uri(prefix_uri)

    client = storage.Client()
    bucket = client.bucket(bucket_name)

    with tempfile.TemporaryDirectory() as tmpdir:
        joblib_path = os.path.join(tmpdir, "model.joblib")
        joblib.dump(model, joblib_path)
        with open(joblib_path, "rb") as joblib_file:
            joblib_bytes = joblib_file.read()

        vertex_dir = vertex_model_dir()
        if vertex_dir is not None:
            shutil.copyfile(joblib_path, vertex_dir / "model.joblib")

    joblib_blob = f"{prefix}/model.joblib"
    joblib_gcs_uri = upload_bytes(
        bucket, joblib_blob, joblib_bytes, content_type="application/octet-stream"
    )

    manifest = build_manifest(
        config_name=config_name,
        model_type=model_type,
        model_run_id=model_run_id,
        model_id=model_id,
        model_family=model_family,
        target_column=target_column,
        features=features or [],
        parameters=parameters,
        model_file="model.joblib",
        joblib_file="model.joblib",
        gcs_prefix=prefix,
    )
    if extra_manifest:
        manifest.update(extra_manifest)

    manifest["joblib_gcs_uri"] = joblib_gcs_uri
    manifest_blob = f"{prefix}/manifest.json"
    manifest_gcs_uri = upload_manifest(bucket, manifest_blob, manifest)

    vertex_dir = vertex_model_dir()
    if vertex_dir is not None:
        (vertex_dir / "manifest.json").write_text(
            json.dumps(manifest, default=str), encoding="utf-8"
        )

    logger.info("Saved joblib model to %s", joblib_gcs_uri)
    return joblib_gcs_uri, manifest_gcs_uri


def load_xgboost_from_gcs(gcs_uri: str):
    """Load XGBoost model saved in native JSON format from GCS."""
    import tempfile

    import xgboost as xgb

    if not gcs_uri.startswith("gs://"):
        raise ValueError(f"Expected gs:// URI, got: {gcs_uri}")
    bucket_name, blob_path = parse_gcs_uri(gcs_uri)
    client = storage.Client()
    model_bytes = client.bucket(bucket_name).blob(blob_path).download_as_bytes()

    model = xgb.XGBRegressor()
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp.write(model_bytes)
        tmp_path = tmp.name
    try:
        model.load_model(tmp_path)
    finally:
        os.unlink(tmp_path)
    return model


def save_xgboost_sklearn_artifacts(
    model: Any,
    *,
    model_run_id: str,
    model_id: str,
    config_name: str,
    model_family: Optional[str],
    model_type: str,
    features: list[str],
    target_column: str,
    parameters: dict[str, Any],
    gcs_model_path: str,
    run_at: Optional[dt] = None,
    include_trees: bool = True,
) -> tuple[str, str, str, str]:
    """
    Persist XGBoost JSON, joblib, manifest (and optional trees) to GCS.

    Returns:
        (json_gcs_uri, joblib_gcs_uri, trees_gcs_uri, manifest_gcs_uri)
    """
    run_at = run_at or dt.utcnow()
    prefix_uri = artifact_prefix(gcs_model_path, config_name, model_type, run_at)
    bucket_name, prefix = parse_gcs_uri(prefix_uri)

    client = storage.Client()
    bucket = client.bucket(bucket_name)

    with tempfile.TemporaryDirectory() as tmpdir:
        json_path = os.path.join(tmpdir, "model.json")
        joblib_path = os.path.join(tmpdir, "model.joblib")
        model.save_model(json_path)
        joblib.dump(model, joblib_path)
        with open(json_path, "rb") as json_file:
            json_bytes = json_file.read()
        with open(joblib_path, "rb") as joblib_file:
            joblib_bytes = joblib_file.read()

        vertex_dir = vertex_model_dir()
        if vertex_dir is not None:
            shutil.copyfile(json_path, vertex_dir / "model.json")
            shutil.copyfile(joblib_path, vertex_dir / "model.joblib")

    json_blob = f"{prefix}/model.json"
    joblib_blob = f"{prefix}/model.joblib"
    json_gcs_uri = upload_bytes(bucket, json_blob, json_bytes, content_type="application/json")
    joblib_gcs_uri = upload_bytes(
        bucket, joblib_blob, joblib_bytes, content_type="application/octet-stream"
    )

    manifest = build_manifest(
        config_name=config_name,
        model_type=model_type,
        model_run_id=model_run_id,
        model_id=model_id,
        model_family=model_family,
        target_column=target_column,
        features=features,
        parameters=parameters,
        gcs_prefix=prefix,
    )
    manifest_blob = f"{prefix}/manifest.json"
    manifest_gcs_uri = upload_manifest(bucket, manifest_blob, manifest)

    trees_gcs_uri = ""
    if include_trees:
        booster = model.get_booster()
        df_trees = booster.trees_to_dataframe()
        df_trees.columns = [column.lower() for column in df_trees.columns]
        trees_blob = f"{prefix}/trees.json"
        trees_gcs_uri = upload_bytes(
            bucket,
            trees_blob,
            df_trees.to_json(orient="records").encode("utf-8"),
            content_type="application/json",
        )

    vertex_dir = vertex_model_dir()
    if vertex_dir is not None:
        (vertex_dir / "manifest.json").write_text(
            json.dumps(manifest, default=str), encoding="utf-8"
        )
        logger.info("Copied artifacts to Vertex AIP_MODEL_DIR: %s", vertex_dir)

    logger.info("Saved model JSON to %s", json_gcs_uri)
    return json_gcs_uri, joblib_gcs_uri, trees_gcs_uri, manifest_gcs_uri


def register_from_manifest(
    *,
    manifest_uri: str,
    display_name: str,
    project_id: str,
    region: str = "us-central1",
    serving_container_image_uri: str = VERTEX_SKLEARN_SERVING_IMAGE,
    artifact_uri: Optional[str] = None,
) -> str:
    """
    Register a trained model in Vertex AI Model Registry from a GCS manifest.

    Returns:
        Model resource name.
    """
    from google.cloud import aiplatform

    bucket_name, blob_path = parse_gcs_uri(manifest_uri)
    client = storage.Client()
    manifest = json.loads(client.bucket(bucket_name).blob(blob_path).download_as_text())

    model_artifact_uri = artifact_uri or manifest.get("joblib_gcs_uri")
    if not model_artifact_uri and manifest.get("gcs_prefix"):
        prefix = manifest["gcs_prefix"].rstrip("/")
        model_file = manifest.get("model_file", "model.joblib")
        model_artifact_uri = f"gs://{bucket_name}/{prefix}/{model_file}"

    if not model_artifact_uri:
        raise ValueError(f"Could not resolve artifact URI from manifest {manifest_uri}")

    aiplatform.init(project=project_id, location=region)
    uploaded = aiplatform.Model.upload(
        display_name=display_name,
        artifact_uri=model_artifact_uri,
        serving_container_image_uri=serving_container_image_uri,
    )
    uploaded.wait()
    logger.info("Registered Vertex model %s from %s", uploaded.resource_name, manifest_uri)
    return uploaded.resource_name
