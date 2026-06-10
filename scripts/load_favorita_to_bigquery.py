#!/usr/bin/env python3
"""
Load Corporación Favorita competition CSVs from GCS into BigQuery.

Expects 7z archives (e.g. train.csv.7z) under a GCS prefix, extracts CSVs locally,
and loads them into tds-favorita.raw_favorita tables used by dbt sources.

Requires Google Cloud credentials (GOOGLE_APPLICATION_CREDENTIALS).

Environment:
    GCS_RAW_DATA_BUCKET: GCS bucket or URI (default: gs://favorita-vertex-ai/source_data)
    GOOGLE_PROJECT_ID: BigQuery project (default: tds-favorita)
    BQ_RAW_DATASET: BigQuery dataset (default: raw_favorita)
    BQ_LOCATION: BigQuery location (default: US)
"""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

import py7zr
from google.cloud import bigquery, storage

from vertex.utils.bigquery_utils import validate_bq_identifier, validate_bq_table_id

DEFAULT_GCS_LOCATION = "gs://favorita-vertex-ai/source_data"
DEFAULT_PROJECT = "tds-favorita"
DEFAULT_DATASET = "raw_favorita"
ARCHIVE_SUFFIXES = (".csv.7z", ".7z")
CSV_SUFFIX = ".csv"

# Kaggle CSV basename (without .csv) -> BigQuery table name in raw_favorita.
# Add entries here for any new competition files; names must match dbt sources in
# dbt/models/raw/schema.yml when used downstream.
CSV_STEM_TO_TABLE: dict[str, str] = {
    "train": "raw_favorita_train",
    "test": "raw_favorita_test",
    "stores": "raw_favorita_stores",
    "oil": "raw_favorita_oil",
    "holidays_events": "raw_favorita_holiday_events",
    "transactions": "raw_favorita_transactions",
    "items": "raw_favorita_items",
    "sample_submission": "raw_favorita_sample_submission",
}


def parse_gcs_location(location: str) -> tuple[str, str]:
    """Parse a bucket name or gs:// URI into (bucket, prefix)."""
    location = location.strip().rstrip("/")
    if location.startswith("gs://"):
        path = location[5:]
        bucket, _, prefix = path.partition("/")
        return bucket, prefix
    return location, ""


def table_name_for_csv(csv_path: Path) -> str | None:
    stem = csv_path.name.removesuffix(CSV_SUFFIX).lower()
    return CSV_STEM_TO_TABLE.get(stem)


def list_archive_blobs(bucket: storage.Bucket, prefix: str) -> list[storage.Blob]:
    prefix = prefix.strip("/")
    search_prefix = f"{prefix}/" if prefix else ""
    blobs: list[storage.Blob] = []
    for blob in bucket.list_blobs(prefix=search_prefix or None):
        name = blob.name.lower()
        if any(name.endswith(suffix) for suffix in ARCHIVE_SUFFIXES):
            blobs.append(blob)
    return sorted(blobs, key=lambda b: b.name)


def list_plain_csv_blobs(bucket: storage.Bucket, prefix: str) -> list[storage.Blob]:
    prefix = prefix.strip("/")
    search_prefix = f"{prefix}/" if prefix else ""
    blobs: list[storage.Blob] = []
    for blob in bucket.list_blobs(prefix=search_prefix or None):
        name = blob.name.lower()
        if name.endswith(CSV_SUFFIX) and not any(
            name.endswith(suffix) for suffix in ARCHIVE_SUFFIXES
        ):
            blobs.append(blob)
    return sorted(blobs, key=lambda b: b.name)


def extract_csvs_from_7z(archive_path: Path, extract_dir: Path) -> list[Path]:
    extract_root = extract_dir.resolve()
    with py7zr.SevenZipFile(archive_path, mode="r") as archive:
        for member in archive.getnames():
            member_path = Path(member)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise ValueError(f"Unsafe path in archive: {member!r}")
            target = (extract_root / member_path).resolve()
            try:
                target.relative_to(extract_root)
            except ValueError as exc:
                raise ValueError(f"Unsafe path in archive: {member!r}") from exc
        archive.extractall(path=extract_root)
    return sorted(
        p for p in extract_root.rglob("*") if p.is_file() and p.suffix.lower() == CSV_SUFFIX
    )


def load_csv_to_bigquery(
    client: bigquery.Client,
    csv_path: Path,
    table_id: str,
    *,
    dry_run: bool = False,
    write_disposition: str = bigquery.WriteDisposition.WRITE_TRUNCATE,
) -> None:
    table_id = validate_bq_table_id(table_id)
    if dry_run:
        print(f"[dry-run] would load {csv_path} -> {table_id}")
        return

    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=1,
        autodetect=True,
        write_disposition=write_disposition,
        allow_quoted_newlines=True,
    )
    with csv_path.open("rb") as handle:
        job = client.load_table_from_file(handle, table_id, job_config=job_config)
    job.result()
    table = client.get_table(table_id)
    print(f"Loaded {csv_path.name} -> {table_id} ({table.num_rows:,} rows)")


def ensure_dataset(
    client: bigquery.Client,
    project: str,
    dataset_id: str,
    location: str,
    *,
    dry_run: bool = False,
) -> None:
    project = validate_bq_identifier(project, label="project")
    dataset_id = validate_bq_identifier(dataset_id, label="dataset")
    dataset_ref = f"{project}.{dataset_id}"
    if dry_run:
        print(f"[dry-run] would ensure dataset {dataset_ref} ({location})")
        return
    dataset = bigquery.Dataset(dataset_ref)
    dataset.location = location
    client.create_dataset(dataset, exists_ok=True)
    print(f"Dataset ready: {dataset_ref}")


def load_favorita_to_bigquery(
    gcs_location: str,
    *,
    project: str,
    dataset: str,
    location: str,
    dry_run: bool = False,
    tables: set[str] | None = None,
    write_disposition: str = bigquery.WriteDisposition.WRITE_TRUNCATE,
) -> list[str]:
    bucket_name, prefix = parse_gcs_location(gcs_location)
    storage_client = storage.Client(project=project)
    bucket = storage_client.bucket(bucket_name)
    bq_client = bigquery.Client(project=project, location=location)

    ensure_dataset(bq_client, project, dataset, location, dry_run=dry_run)

    loaded_tables: list[str] = []
    archive_blobs = list_archive_blobs(bucket, prefix)
    if not archive_blobs:
        raise FileNotFoundError(
            f"No 7z archives ({', '.join(ARCHIVE_SUFFIXES)}) found under "
            f"gs://{bucket_name}/{prefix}/"
        )

    print(
        f"Found {len(archive_blobs)} archive(s) under gs://{bucket_name}/{prefix or ''}/"
    )

    with tempfile.TemporaryDirectory(prefix="favorita-bq-load-") as tmp:
        tmp_dir = Path(tmp)
        for blob in archive_blobs:
            archive_path = tmp_dir / Path(blob.name).name
            gcs_uri = f"gs://{bucket_name}/{blob.name}"
            print(f"Downloading {gcs_uri}")
            if not dry_run:
                blob.download_to_filename(str(archive_path))

            if dry_run:
                # Infer targets from blob name when we are not downloading.
                stem = Path(blob.name).name
                for suffix in ARCHIVE_SUFFIXES:
                    if stem.lower().endswith(suffix):
                        stem = stem[: -len(suffix)]
                        break
                table_name = CSV_STEM_TO_TABLE.get(stem.removesuffix(CSV_SUFFIX).lower())
                if table_name and (tables is None or table_name in tables):
                    table_id = f"{project}.{dataset}.{table_name}"
                    print(f"[dry-run] would extract and load -> {table_id}")
                    loaded_tables.append(table_id)
                continue

            extract_dir = tmp_dir / Path(blob.name).stem
            extract_dir.mkdir(parents=True, exist_ok=True)
            csv_files = extract_csvs_from_7z(archive_path, extract_dir)
            if not csv_files:
                raise FileNotFoundError(f"No CSV files extracted from {gcs_uri}")

            for csv_path in csv_files:
                table_name = table_name_for_csv(csv_path)
                if table_name is None:
                    print(f"Skipping unmapped CSV: {csv_path.name}")
                    continue
                if tables is not None and table_name not in tables:
                    continue
                table_id = f"{project}.{dataset}.{table_name}"
                load_csv_to_bigquery(
                    bq_client,
                    csv_path,
                    table_id,
                    dry_run=dry_run,
                    write_disposition=write_disposition,
                )
                loaded_tables.append(table_id)

        # Also load uncompressed CSVs if present (e.g. from load_favorita_to_gcs).
        for blob in list_plain_csv_blobs(bucket, prefix):
            table_name = table_name_for_csv(Path(blob.name))
            if table_name is None:
                continue
            if tables is not None and table_name not in tables:
                continue
            csv_path = tmp_dir / Path(blob.name).name
            gcs_uri = f"gs://{bucket_name}/{blob.name}"
            print(f"Downloading {gcs_uri}")
            if not dry_run:
                blob.download_to_filename(str(csv_path))
            table_id = f"{project}.{dataset}.{table_name}"
            load_csv_to_bigquery(
                bq_client,
                csv_path,
                table_id,
                dry_run=dry_run,
                write_disposition=write_disposition,
            )
            loaded_tables.append(table_id)

    return loaded_tables


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load Favorita 7z CSV archives from GCS into BigQuery raw_favorita."
    )
    parser.add_argument(
        "--gcs-location",
        default=os.environ.get("GCS_RAW_DATA_BUCKET", DEFAULT_GCS_LOCATION),
        help="GCS bucket or gs:// URI (default: GCS_RAW_DATA_BUCKET or favorita source_data).",
    )
    parser.add_argument(
        "--project",
        default=os.environ.get("GOOGLE_PROJECT_ID", DEFAULT_PROJECT),
        help="BigQuery project id (default: GOOGLE_PROJECT_ID or tds-favorita).",
    )
    parser.add_argument(
        "--dataset",
        default=os.environ.get("BQ_RAW_DATASET", DEFAULT_DATASET),
        help="BigQuery dataset id (default: BQ_RAW_DATASET or raw_favorita).",
    )
    parser.add_argument(
        "--location",
        default=os.environ.get("BQ_LOCATION", "US"),
        help="BigQuery dataset location (default: BQ_LOCATION or US).",
    )
    parser.add_argument(
        "--table",
        action="append",
        dest="tables",
        metavar="TABLE",
        help="Load only this raw table (e.g. raw_favorita_train). Repeatable.",
    )
    parser.add_argument(
        "--write-disposition",
        default=bigquery.WriteDisposition.WRITE_TRUNCATE,
        choices=[
            bigquery.WriteDisposition.WRITE_TRUNCATE,
            bigquery.WriteDisposition.WRITE_APPEND,
            bigquery.WriteDisposition.WRITE_EMPTY,
        ],
        help="BigQuery write disposition (default: WRITE_TRUNCATE).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List planned loads without downloading or writing to BigQuery.",
    )
    args = parser.parse_args()

    table_filter = set(args.tables) if args.tables else None
    load_favorita_to_bigquery(
        args.gcs_location,
        project=args.project,
        dataset=args.dataset,
        location=args.location,
        dry_run=args.dry_run,
        tables=table_filter,
        write_disposition=args.write_disposition,
    )


if __name__ == "__main__":
    main()
