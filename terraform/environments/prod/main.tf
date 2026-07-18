module "gcp_apis" {
  source     = "../../modules/gcp-apis"
  project_id = var.project_id
}

module "artifact_registry" {
  source     = "../../modules/artifact-registry"
  project_id = var.project_id
  region     = var.region
  repo_name  = var.repo_name

  depends_on = [
    module.gcp_apis,
    module.bigquery_datasets,
    module.gcs_buckets,
  ]
}

module "iam_vertex_sa" {
  source        = "../../modules/iam-vertex-sa"
  project_id    = var.project_id
  sa_id         = var.sa_id
  caller_member = var.caller_member
  bucket_names = [
    "${var.client_label}-raw",
    "${var.client_label}-vertex-staging",
    "${var.client_label}-vertex-models",
    "${var.client_label}-mlflow",
  ]
  dataset_ids = [
    var.raw_dataset,
    var.dbt_dataset,
  ]
  prediction_bucket_names = ["${var.client_label}-vertex-models"]
  prediction_dataset_ids  = [var.dbt_dataset]

  depends_on = [module.gcp_apis]
}

module "bigquery_datasets" {
  source       = "../../modules/bigquery-datasets"
  project_id   = var.project_id
  dbt_dataset  = var.dbt_dataset
  raw_dataset  = var.raw_dataset
  environment  = var.environment
  client_label = var.client_label

  depends_on = [module.gcp_apis]
}

module "gcs_buckets" {
  source        = "../../modules/gcs-buckets"
  project_id    = var.project_id
  region        = var.bucket_location
  client_label  = var.client_label
  environment   = var.environment
  force_destroy = false

  depends_on = [module.gcp_apis]
}

# Scaffolded but disabled — no Cloud Run trigger service exists yet (docs/iac.md Scheduling
# Pattern A). Set enabled = true and populate jobs once one does.
module "cloud_scheduler" {
  source     = "../../modules/cloud-scheduler"
  project_id = var.project_id
  region     = var.region
  enabled    = false
}
