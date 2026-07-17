output "raw_dataset_id" {
  value = google_bigquery_dataset.raw.dataset_id
}

output "analytics_dataset_id" {
  value = google_bigquery_dataset.analytics.dataset_id
}
