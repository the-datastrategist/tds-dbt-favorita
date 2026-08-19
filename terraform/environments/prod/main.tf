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

module "monitoring_alerts" {
  source = "../../modules/monitoring-alerts"

  project_id               = var.project_id
  enabled                  = var.enable_monitoring_alerts
  notification_channel_ids = var.monitoring_notification_channel_ids

  depends_on = [module.gcp_apis]
}

module "monitoring_runner" {
  source = "../../modules/monitoring-runner"

  project_id              = var.project_id
  region                  = var.region
  enabled                 = var.enable_monitoring_runner
  container_image         = var.monitoring_runner_image
  service_account_email   = module.iam_vertex_sa.email
  slack_webhook_secret_id = var.monitoring_slack_webhook_secret_id
  dbt_dataset             = var.dbt_dataset
  raw_dataset             = var.raw_dataset
  schedule                = var.monitoring_runner_schedule

  depends_on = [module.gcp_apis, module.monitoring_alerts]
}

module "forecast_api" {
  source = "../../modules/forecast-api"

  project_id                            = var.project_id
  region                                = var.region
  enabled                               = var.enable_forecast_api
  enable_lifecycle_mutations            = var.enable_forecast_api_mutations
  lifecycle_role_members                = var.forecastlab_lifecycle_role_members
  enable_publication_webhook            = var.enable_forecast_publication_webhook
  publication_webhook_url_secret_id     = var.forecast_publication_webhook_url_secret_id
  publication_webhook_signing_secret_id = var.forecast_publication_webhook_signing_secret_id
  publication_webhook_name              = var.forecast_publication_webhook_name
  container_image                       = var.forecast_api_image
  dbt_dataset                           = var.dbt_dataset
  invoker_members                       = var.forecast_api_invoker_members
  enable_iap                            = var.enable_forecastlab_iap
  iap_access_members                    = var.forecastlab_iap_access_members
  min_instance_count                    = var.forecast_api_min_instances
  max_instance_count                    = var.forecast_api_max_instances

  depends_on = [module.gcp_apis, module.bigquery_datasets]
}
