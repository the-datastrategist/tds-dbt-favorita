"""Resolve training hyperparameters from optimize runs (GCS + BigQuery)."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime as dt
from typing import Any, Optional

from vertex.config.load_config import load_all_configs
from vertex.utils.artifacts import parse_gcs_uri, upload_bytes
from google.cloud import bigquery, storage

logger = logging.getLogger(__name__)

BEST_PARAMS_FILENAME = "latest_best_params.json"


def infer_optimize_config_name(train_config_name: str) -> Optional[str]:
    """Map favorita_xgboost_train -> favorita_xgboost_optimize when present in YAML."""
    if train_config_name.endswith("_train"):
        candidate = f"{train_config_name[:-6]}_optimize"
    elif "_train_" in train_config_name:
        candidate = train_config_name.replace("_train_", "_optimize_", 1)
    else:
        return None
    try:
        names = {cfg.get("name") for cfg in load_all_configs()}
        if candidate in names:
            return candidate
    except (ValueError, FileNotFoundError):
        pass
    return None


def best_params_gcs_uri(gcs_model_path: str, optimize_config_name: str) -> str:
    bucket_name, base_prefix = parse_gcs_uri(gcs_model_path)
    if base_prefix and not base_prefix.endswith("/"):
        base_prefix = f"{base_prefix}/"
    blob_path = f"{base_prefix}optimize/{optimize_config_name}/{BEST_PARAMS_FILENAME}"
    return f"gs://{bucket_name}/{blob_path}"


def persist_best_params(
    config: dict[str, Any],
    optimize_result: dict[str, Any],
) -> str:
    """
    Write canonical best-params JSON to GCS for downstream train steps.

    Returns:
        gs:// URI of the written object.
    """
    inputs = config.get("inputs") or {}
    spec_name = config.get("name")
    gcs_model_path = inputs.get("gcs_model_path")
    if not gcs_model_path:
        raise ValueError("inputs.gcs_model_path required to persist best params")

    optimize_config_name = spec_name
    uri = best_params_gcs_uri(gcs_model_path, optimize_config_name)
    bucket_name, blob_path = parse_gcs_uri(uri)

    payload = {
        "optimize_config_name": optimize_config_name,
        "optimize_run_id": optimize_result.get("optimize_run_id"),
        "best_trial_number": optimize_result.get("best_trial_number"),
        "best_value": optimize_result.get("best_value"),
        "best_params": optimize_result.get("best_params") or {},
        "model_family": config.get("model_family"),
        "model_type": (config.get("job") or {}).get("model_type"),
        "written_at": dt.utcnow().isoformat(),
    }

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    upload_bytes(
        bucket,
        blob_path,
        json.dumps(payload, default=str).encode("utf-8"),
        content_type="application/json",
    )
    logger.info("Persisted best params to %s", uri)
    os.environ["VERTEX_BEST_PARAMS_URI"] = uri
    if payload.get("optimize_run_id"):
        os.environ["VERTEX_OPTIMIZE_RUN_ID"] = str(payload["optimize_run_id"])
    return uri


def load_best_params_from_gcs(gcs_uri: str) -> Optional[dict[str, Any]]:
    if not gcs_uri.startswith("gs://"):
        return None
    bucket_name, blob_path = parse_gcs_uri(gcs_uri)
    client = storage.Client()
    blob = client.bucket(bucket_name).blob(blob_path)
    if not blob.exists():
        return None
    return json.loads(blob.download_as_text())


def load_best_params_from_bq(
    optimize_table: str,
    optimize_config_name: str,
    *,
    optimize_run_id: Optional[str] = None,
    project_id: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Load best trial parameters from the optimize trials table."""
    run_clause = ""
    params = [
        bigquery.ScalarQueryParameter("config_name", "STRING", optimize_config_name),
    ]
    if optimize_run_id:
        run_clause = "AND optimize_run_id = @optimize_run_id"
        params.append(
            bigquery.ScalarQueryParameter("optimize_run_id", "STRING", optimize_run_id)
        )
    query = f"""
        WITH latest_run AS (
            SELECT optimize_run_id
            FROM `{optimize_table}`
            WHERE config_name = @config_name
            {run_clause}
            ORDER BY run_at DESC
            LIMIT 1
        )
        SELECT
            t.optimize_run_id,
            t.trial_number AS best_trial_number,
            t.objective_value AS best_value,
            t.parameters AS best_params
        FROM `{optimize_table}` AS t
        INNER JOIN latest_run AS lr ON t.optimize_run_id = lr.optimize_run_id
        ORDER BY t.objective_value ASC
        LIMIT 1
    """
    project_id = project_id or os.getenv("GOOGLE_PROJECT_ID")
    client = bigquery.Client(project=project_id)
    job_config = bigquery.QueryJobConfig(query_parameters=params)
    try:
        frame = client.query(query, job_config=job_config).to_dataframe()
    except Exception as exc:
        logger.warning("Could not load best params from BQ (%s): %s", optimize_table, exc)
        return None
    if frame.empty:
        return None
    row = frame.iloc[0]
    params = row.get("best_params")
    if isinstance(params, str):
        params = json.loads(params)
    return {
        "optimize_run_id": row.get("optimize_run_id"),
        "best_trial_number": int(row["best_trial_number"])
        if row.get("best_trial_number") is not None
        else None,
        "best_value": float(row["best_value"]) if row.get("best_value") is not None else None,
        "best_params": params or {},
        "source": "bigquery",
    }


def resolve_model_parameters(
    config: dict[str, Any],
    defaults: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
  Merge model_params for training.

  Precedence: YAML model_params < GCS latest_best_params < explicit optimize_run_id pin.
  Set inputs.use_optimized_params: false to skip optimize lookup.
    """
    inputs = config.get("inputs") or {}
    outputs = config.get("outputs") or {}
    config_name = config.get("name", "")

    base_params = dict(defaults)
    base_params.update(inputs.get("model_params") or {})

    provenance: dict[str, Any] = {
        "params_source": "config",
        "optimize_config_name": None,
        "optimize_run_id": None,
        "best_params_uri": None,
    }

    if inputs.get("use_optimized_params") is False:
        return base_params, provenance

    optimize_config_name = (
        inputs.get("optimize_config_name")
        or os.getenv("VERTEX_OPTIMIZE_CONFIG_NAME")
        or infer_optimize_config_name(config_name)
    )
    if not optimize_config_name:
        return base_params, provenance

    provenance["optimize_config_name"] = optimize_config_name
    optimize_run_id = (
        inputs.get("optimize_run_id")
        or os.getenv("VERTEX_OPTIMIZE_RUN_ID")
        or None
    )
    provenance["optimize_run_id"] = optimize_run_id

    gcs_model_path = inputs.get("gcs_model_path")
    best_record: Optional[dict[str, Any]] = None
    if gcs_model_path:
        uri = (
            os.getenv("VERTEX_BEST_PARAMS_URI")
            or best_params_gcs_uri(gcs_model_path, optimize_config_name)
        )
        provenance["best_params_uri"] = uri
        best_record = load_best_params_from_gcs(uri)

    if not best_record:
        optimize_table = outputs.get("optimize_table")
        if optimize_table:
            best_record = load_best_params_from_bq(
                optimize_table,
                optimize_config_name,
                optimize_run_id=optimize_run_id,
                project_id=inputs.get("project_id"),
            )

    if not best_record or not best_record.get("best_params"):
        logger.info(
            "No optimized params found for %s; using config model_params",
            optimize_config_name,
        )
        return base_params, provenance

    merged = {**base_params, **dict(best_record["best_params"])}
    provenance.update(
        {
            "params_source": best_record.get("source", "optimize"),
            "optimize_run_id": best_record.get("optimize_run_id"),
            "best_trial_number": best_record.get("best_trial_number"),
            "best_value": best_record.get("best_value"),
        }
    )
    logger.info(
        "Training %s with optimized params from %s (run_id=%s)",
        config_name,
        optimize_config_name,
        provenance.get("optimize_run_id"),
    )
    return merged, provenance
