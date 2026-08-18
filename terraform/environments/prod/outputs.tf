output "vertex_service_account_email" {
  description = "Set as VERTEX_PIPELINE_SERVICE_ACCOUNT in .env."
  value       = module.iam_vertex_sa.email
}

output "vertex_prediction_service_account_email" {
  description = "Prediction-only Vertex service account email."
  value       = module.iam_vertex_sa.prediction_email
}

output "artifact_registry_url" {
  description = "Docker push target for `make vertex-docker-push`."
  value       = module.artifact_registry.repository_url
}

output "gcs_bucket_names" {
  value = module.gcs_buckets.bucket_names
}

output "bigquery_dataset_ids" {
  value = {
    raw       = module.bigquery_datasets.raw_dataset_id
    analytics = module.bigquery_datasets.analytics_dataset_id
  }
}

output "forecast_api_url" {
  description = "Authenticated Forecast Retrieval API URL when enabled."
  value       = module.forecast_api.service_url
}
