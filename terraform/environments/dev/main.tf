module "gcp_apis" {
  source     = "../../modules/gcp-apis"
  project_id = var.project_id
}

module "artifact_registry" {
  source     = "../../modules/artifact-registry"
  project_id = var.project_id
  region     = var.region
  repo_name  = var.repo_name

  depends_on = [module.gcp_apis]
}

module "iam_vertex_sa" {
  source        = "../../modules/iam-vertex-sa"
  project_id    = var.project_id
  sa_id         = var.sa_id
  caller_member = var.caller_member
  bucket_names = concat(
    values(module.gcs_buckets.bucket_names),
    compact([module.gcs_buckets.mlflow_bucket_name]),
  )
  dataset_ids = [
    module.bigquery_datasets.raw_dataset_id,
    module.bigquery_datasets.analytics_dataset_id,
  ]
  prediction_bucket_names = [module.gcs_buckets.bucket_names["models"]]
  prediction_dataset_ids  = [module.bigquery_datasets.analytics_dataset_id]

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
  source       = "../../modules/gcs-buckets"
  project_id   = var.project_id
  region       = var.region
  client_label = var.client_label
  environment  = var.environment

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
