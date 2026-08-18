#!/usr/bin/env python3
"""Export one immutable published forecast run from BigQuery to Cloud Storage."""

from __future__ import annotations

import argparse
import json
import re

from google.cloud import bigquery

from vertex.utils.bigquery_utils import validate_bq_table_id

RUN_ID = re.compile(r"^[a-f0-9]{64}$")
GCS_URI = re.compile(r"^gs://[a-z0-9][a-z0-9._-]{1,221}/[^'\n\r]*\*[^'\n\r]*$")


def export_forecast(
    *,
    project_id: str,
    source_view: str,
    forecast_run_id: str,
    publication_version: int,
    destination: str,
    format: str,
) -> dict[str, str]:
    if not RUN_ID.fullmatch(forecast_run_id):
        raise ValueError("forecast_run_id must be a 64-character lowercase hex digest")
    if publication_version < 1:
        raise ValueError("publication_version must be a positive integer")
    if not GCS_URI.fullmatch(destination) or destination.count("*") != 1:
        raise ValueError("destination must be a safe gs:// object pattern containing one wildcard")
    export_format = format.upper()
    if export_format not in {"CSV", "PARQUET"}:
        raise ValueError("format must be csv or parquet")
    table = validate_bq_table_id(source_view)
    options = [f"uri='{destination}'", f"format='{export_format}'", "overwrite=false"]
    if export_format == "CSV":
        options.append("header=true")
    query = f"""
    EXPORT DATA OPTIONS ({', '.join(options)}) AS
    SELECT * FROM `{table}`
    WHERE forecast_run_id = @forecast_run_id
      AND publication_version = @publication_version
    """
    client = bigquery.Client(project=project_id)
    client.query(
        query,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("forecast_run_id", "STRING", forecast_run_id),
                bigquery.ScalarQueryParameter("publication_version", "INT64", publication_version),
            ]
        ),
    ).result()
    return {
        "forecast_run_id": forecast_run_id,
        "publication_version": str(publication_version),
        "source_view": table,
        "destination": destination,
        "format": export_format,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--forecast-run-id", required=True)
    parser.add_argument("--publication-version", required=True, type=int)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--format", default="parquet", choices=("csv", "parquet"))
    parser.add_argument("--project-id", default="tds-favorita")
    parser.add_argument("--source-view", default="tds-favorita.favorita.published_forecasts_by_run")
    print(json.dumps(export_forecast(**vars(parser.parse_args())), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
