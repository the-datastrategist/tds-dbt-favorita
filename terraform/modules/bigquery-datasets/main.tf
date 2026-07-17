# Scoped to dataset-level resources only (location, labels). Table schemas
# (vertex/ddl/vertex_bq_tables.sql, dbt models) keep their own IF NOT EXISTS / ADD COLUMN
# IF NOT EXISTS ownership — see docs/specs/terraform_modules.md Non-goals.

resource "google_bigquery_dataset" "raw" {
  project    = var.project_id
  dataset_id = var.raw_dataset
  location   = var.bq_location

  labels = {
    environment = var.environment
    client      = var.client_label
  }
}

resource "google_bigquery_dataset" "analytics" {
  project    = var.project_id
  dataset_id = var.dbt_dataset
  location   = var.bq_location

  labels = {
    environment = var.environment
    client      = var.client_label
  }
}
