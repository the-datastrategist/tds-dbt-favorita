# One bucket per purpose per docs/iac.md's GCS layout table (raw, staging, models), plus an
# optional mlflow bucket. The environment passes these bucket names to iam-vertex-sa so
# object access is granted only on platform-owned buckets.

locals {
  labels = {
    environment = var.environment
    client      = var.client_label
  }

  buckets = {
    raw     = "${var.client_label}-raw"
    staging = "${var.client_label}-vertex-staging"
    models  = "${var.client_label}-vertex-models"
  }
}

resource "google_storage_bucket" "buckets" {
  for_each = local.buckets

  project       = var.project_id
  name          = each.value
  location      = var.region
  force_destroy = var.force_destroy
  labels        = local.labels

  uniform_bucket_level_access = true
}

resource "google_storage_bucket" "mlflow" {
  count = var.enable_mlflow_bucket ? 1 : 0

  project       = var.project_id
  name          = "${var.client_label}-mlflow"
  location      = var.region
  force_destroy = var.force_destroy
  labels        = local.labels

  uniform_bucket_level_access = true
}
