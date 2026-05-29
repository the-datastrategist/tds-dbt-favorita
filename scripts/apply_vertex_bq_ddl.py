#!/usr/bin/env python3
"""Apply Vertex ML BigQuery DDL from vertex/ddl/vertex_bq_tables.sql."""

from __future__ import annotations

import re
from pathlib import Path

from google.cloud import bigquery

DDL_PATH = Path(__file__).resolve().parent.parent / "vertex" / "ddl" / "vertex_bq_tables.sql"


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


def main() -> None:
    ddl = DDL_PATH.read_text()
    client = bigquery.Client()
    for stmt in _statements(ddl):
        job = client.query(stmt)
        job.result()
        match = re.search(r"`([^`]+)`", stmt)
        label = match.group(1) if match else stmt.split()[0]
        kind = "Altered" if stmt.upper().startswith("ALTER") else "Created"
        print(f"{kind}: {label}")


if __name__ == "__main__":
    main()
