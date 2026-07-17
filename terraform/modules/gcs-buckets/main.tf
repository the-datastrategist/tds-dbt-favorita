# One bucket per purpose per docs/iac.md's GCS layout table (raw, staging, models), plus an
# optional mlflow bucket. Bucket-level IAM (not project-wide storage admin) is granted by
# iam-vertex-sa's roles/storage.objectAdmin at the SA level; per-bucket bindings can be added
# here later if a client needs tighter scoping than project-wide storage.objectAdmin.

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
