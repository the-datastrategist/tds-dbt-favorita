#!/usr/bin/env python3
"""Apply Vertex ML BigQuery DDL from vertex/ddl/vertex_bq_tables.sql.

Environment:
    BQ_LOCATION: BigQuery dataset location used when a referenced dataset
        does not exist yet and must be created (default: US).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from google.cloud import bigquery

from vertex.utils.bigquery_utils import validate_bq_identifier

DDL_PATH = Path(__file__).resolve().parent.parent / "vertex" / "ddl" / "vertex_bq_tables.sql"
DATASET_REF_PATTERN = re.compile(r"`([\w-]+)\.([\w-]+)\.[\w-]+`")


def _statements(ddl: str) -> list[str]:
    """Split DDL file into executable statements (CREATE / ALTER only)."""
    statements: list[str] = []
    buffer: list[str] = []
    for line in ddl.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        buffer.append(line)
        if stripped.endswith(";"):
            stmt = "\n".join(buffer).strip()
            buffer = []
            upper = stmt.upper()
            if "CREATE TABLE" in upper or upper.startswith("ALTER TABLE"):
                statements.append(stmt.rstrip(";").strip())
    return statements


def _dataset_ids(ddl: str) -> list[str]:
    """Distinct `project.dataset` ids referenced by fully-qualified table refs in the DDL."""
    seen: list[str] = []
    for project, dataset in DATASET_REF_PATTERN.findall(ddl):
        dataset_id = f"{project}.{dataset}"
        if dataset_id not in seen:
            seen.append(dataset_id)
    return seen


def _ensure_datasets(client: bigquery.Client, ddl: str, location: str) -> None:
    """Create any dataset referenced by the DDL that doesn't already exist."""
    for dataset_id in _dataset_ids(ddl):
        project, dataset = dataset_id.split(".")
        validate_bq_identifier(project, label="project")
        validate_bq_identifier(dataset, label="dataset")
        dataset_ref = bigquery.Dataset(dataset_id)
        dataset_ref.location = location
        client.create_dataset(dataset_ref, exists_ok=True)
        print(f"Dataset ready: {dataset_id} (location={location})")


def main() -> None:
    ddl = DDL_PATH.read_text()
    location = os.environ.get("BQ_LOCATION", "US")
    client = bigquery.Client()
    _ensure_datasets(client, ddl, location)
    for stmt in _statements(ddl):
        job = client.query(stmt)
        job.result()
        match = re.search(r"`([^`]+)`", stmt)
        label = match.group(1) if match else stmt.split()[0]
        kind = "Altered" if stmt.upper().startswith("ALTER") else "Created"
        print(f"{kind}: {label}")


if __name__ == "__main__":
    main()
