#!/usr/bin/env python3
"""Write and verify one canonical seven-day forecast in BigQuery.

This is intentionally explicit and mutating. It only writes when --confirm-write
is supplied, and retries are safe because the writer uses stable IDs and MERGE.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

import pandas as pd
from google.cloud import bigquery

from vertex.utils.forecast_outputs import write_forecast_outputs_if_configured
from vertex.utils.predictions import build_standard_prediction_rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--dataset", default="favorita")
    parser.add_argument("--confirm-write", action="store_true")
    args = parser.parse_args()
    if not args.confirm_write:
        parser.error("--confirm-write is required because this smoke test writes BigQuery rows")

    prefix = f"{args.project}.{args.dataset}"
    run_at = datetime.now(timezone.utc).replace(microsecond=0)
    source = pd.DataFrame(
        {"store_nbr": [-987654], "date": [pd.Timestamp(run_at.date())], "sales": [0.0]}
    )
    predictions = build_standard_prediction_rows(
        source,
        pd.Series([0.0]),
        predict_run_id=f"forecast-contract-smoke-{run_at:%Y%m%d%H%M%S}",
        model_id="forecast-contract-smoke-model-v1",
        model_run_id="forecast-contract-smoke-training-v1",
        config_name="forecast_contract_smoke",
        model_family="smoke_test",
        model_type="deterministic_smoke",
        target_column="sales",
        run_at=run_at,
        id_columns=["store_nbr"],
        forecast_horizon=7,
        model_artifact_uri="gs://forecast-contract-smoke/model-v1",
    )
    config = {
        "inputs": {"feature_version": "forecast-contract-smoke-features-v1"},
        "outputs": {
            "forecast_contract_path": "vertex/config/forecast_contract.yaml",
            "forecast_contract_table": f"{prefix}.forecast_contracts",
            "forecast_runs_table": f"{prefix}.forecast_runs",
            "forecast_output_table": f"{prefix}.forecast_outputs",
            "forecast_status_history_table": f"{prefix}.forecast_status_history",
        },
    }
    written = write_forecast_outputs_if_configured(
        config=config, prediction_rows=predictions, project_id=args.project
    )

    client = bigquery.Client(project=args.project)
    query = f"""
      SELECT
        COUNT(*) AS row_count,
        COUNTIF(
          forecast_origin IS NOT NULL AND target_date IS NOT NULL AND horizon = 7
          AND model_id IS NOT NULL AND feature_version IS NOT NULL
          AND code_sha IS NOT NULL AND data_cutoff IS NOT NULL
          AND forecast_status = 'draft'
        ) AS valid_count
      FROM `{prefix}.forecast_outputs`
      WHERE forecast_run_id = @forecast_run_id
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter(
                "forecast_run_id", "STRING", predictions["predict_run_id"].iloc[0]
            )
        ]
    )
    result = next(iter(client.query(query, job_config=job_config).result()))
    if result.row_count != written or result.valid_count != written:
        raise RuntimeError(
            f"smoke verification failed: written={written}, rows={result.row_count}, "
            f"valid={result.valid_count}"
        )
    print(f"Verified {written} canonical seven-day forecast row(s).")


if __name__ == "__main__":
    main()
