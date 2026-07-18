#!/usr/bin/env python3
"""Live acceptance for canonical horizon-7 forecast persistence and publication."""

from __future__ import annotations

import argparse
import json
import re
from typing import Any

from orchestration.flows.forecast_publication import run_forecast_publication_cycle
from vertex.config.load_config import load_model_config
from vertex.utils.bigquery_utils import run_query
from vertex.utils.data_utils import get_hash
from vertex.utils.forecast_outputs import write_forecast_outputs_if_configured

DEFAULT_CONTRACT = "vertex/config/forecast_contract_acceptance_h7.yaml"
DEFAULT_CONFIG = "favorita_store_h7_xgboost"
DEFAULT_TABLE_PREFIX = "tds-favorita.favorita"
RUN_ID_PATTERN = re.compile(r"^[a-f0-9]{64}$")


def _source_predictions(run_id: str, table_prefix: str, project_id: str):
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError("source prediction run id must be a 64-character lowercase hex digest")
    return run_query(
        f"""
        SELECT
          prediction_id,
          predict_run_id,
          model_run_id,
          model_id,
          config_name,
          model_family,
          model_type,
          run_at,
          date,
          forecast_date,
          forecast_horizon,
          prediction,
          COALESCE(prediction_lower, prediction) AS prediction_lower,
          COALESCE(prediction_upper, prediction) AS prediction_upper,
          model_artifact_uri,
          store_id,
          'entity_model' AS forecast_strategy,
          'high' AS confidence_flag,
          'acceptance_passthrough' AS calibration_method,
          CONCAT('acceptance-', predict_run_id) AS calibration_run_id,
          'none' AS reconciliation_method
        FROM `{table_prefix}.ml_model_predictions`
        WHERE predict_run_id = '{run_id}'
          AND forecast_horizon = 7
        ORDER BY store_id
        """,
        project_id=project_id,
    )


def _acceptance_summary(run_id: str, table_prefix: str, project_id: str) -> dict[str, Any]:
    rows = (
        run_query(
            f"""
        SELECT
          COUNT(*) AS output_count,
          COUNT(DISTINCT entity_key_json) AS entity_count,
          COUNTIF(horizon != 7 OR DATE_DIFF(target_date, DATE(forecast_origin), DAY) != 7)
            AS invalid_horizon_count,
          COUNTIF(
            contract_enforced IS NOT TRUE
            OR forecast_origin IS NULL OR target_date IS NULL OR model_run_id IS NULL
            OR model_id IS NULL OR feature_version IS NULL OR code_sha IS NULL
            OR data_cutoff IS NULL OR forecast_contract_hash IS NULL
            OR forecast_status IS NULL OR forecast_strategy IS NULL
            OR calibration_method IS NULL OR calibration_run_id IS NULL
            OR reconciliation_method IS NULL
          ) AS missing_lineage_count,
          COUNTIF(prediction_p10 > prediction_p50 OR prediction_p50 > prediction_p90)
            AS invalid_quantile_count
        FROM `{table_prefix}.forecast_outputs`
        WHERE forecast_run_id = '{run_id}'
        """,
            project_id=project_id,
        )
        .iloc[0]
        .to_dict()
    )
    lifecycle = (
        run_query(
            f"""
        SELECT
          COUNT(DISTINCT approval_id) AS approval_count,
          COUNT(DISTINCT publication_id) AS publication_count,
          COUNTIF(delivery_status IS NULL) AS missing_delivery_status_count
        FROM `{table_prefix}.forecast_publications` AS publications
        LEFT JOIN `{table_prefix}.forecast_approvals` AS approvals
          USING (approval_id, forecast_output_id, forecast_run_id)
        WHERE publications.forecast_run_id = '{run_id}'
        """,
            project_id=project_id,
        )
        .iloc[0]
        .to_dict()
    )
    return {**rows, **lifecycle}


def run_acceptance(
    *, source_run_id: str, project_id: str, table_prefix: str = DEFAULT_TABLE_PREFIX
) -> dict[str, Any]:
    predictions = _source_predictions(source_run_id, table_prefix, project_id)
    if predictions.empty:
        raise RuntimeError(f"no horizon-7 predictions found for {source_run_id}")
    if predictions["store_id"].isna().any():
        raise RuntimeError("source predictions contain null store_id values")

    acceptance_run_id = get_hash(
        {"acceptance": "canonical-contract-h7-v2", "source_prediction_run_id": source_run_id}
    )
    predictions["predict_run_id"] = acceptance_run_id
    predictions["calibration_run_id"] = f"acceptance-{acceptance_run_id}"

    config = load_model_config(DEFAULT_CONFIG)
    config["outputs"] = {
        **config["outputs"],
        "forecast_contract_path": DEFAULT_CONTRACT,
        "forecast_status": "draft",
    }
    cutoff = predictions["date"].max()
    cutoff_metadata = {
        "data_cutoff": cutoff,
        "source_cutoff_json": json.dumps({"ml_model_predictions": str(cutoff)}, sort_keys=True),
        "feature_availability_hash": get_hash({"acceptance_source": source_run_id}),
        "feature_materialization_id": f"acceptance-{source_run_id[:16]}",
    }
    written = write_forecast_outputs_if_configured(
        config=config,
        prediction_rows=predictions,
        project_id=project_id,
        feature_cutoff_metadata=cutoff_metadata,
    )
    publication = run_forecast_publication_cycle(
        forecast_run_id=acceptance_run_id,
        contract_path=DEFAULT_CONTRACT,
        publication_mode="auto_publish",
        idempotency_key=f"canonical-contract-acceptance-{acceptance_run_id}",
        actor="canonical-contract-acceptance",
        destination="canonical_bigquery_acceptance",
        table_prefix=table_prefix,
        project_id=project_id,
    )
    summary = _acceptance_summary(acceptance_run_id, table_prefix, project_id)
    expected = len(predictions)
    required_zero = (
        "invalid_horizon_count",
        "missing_lineage_count",
        "invalid_quantile_count",
        "missing_delivery_status_count",
    )
    if int(summary["output_count"]) != expected or int(summary["entity_count"]) != expected:
        raise RuntimeError(f"canonical cardinality mismatch: expected {expected}, got {summary}")
    if any(int(summary[field]) != 0 for field in required_zero):
        raise RuntimeError(f"canonical acceptance invariants failed: {summary}")
    if int(summary["approval_count"]) != expected or int(summary["publication_count"]) != expected:
        raise RuntimeError(f"publication cardinality mismatch: expected {expected}, got {summary}")
    return {
        "source_prediction_run_id": source_run_id,
        "forecast_run_id": acceptance_run_id,
        "source_prediction_count": expected,
        "canonical_rows_written": written,
        "publication": publication,
        **{key: int(value) for key, value in summary.items()},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run-id", required=True)
    parser.add_argument("--project-id", default="tds-favorita")
    parser.add_argument("--table-prefix", default=DEFAULT_TABLE_PREFIX)
    args = parser.parse_args()
    print(
        json.dumps(
            run_acceptance(
                source_run_id=args.source_run_id,
                project_id=args.project_id,
                table_prefix=args.table_prefix,
            ),
            indent=2,
            sort_keys=True,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
