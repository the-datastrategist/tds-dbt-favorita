output "email" {
  description = "Set as VERTEX_PIPELINE_SERVICE_ACCOUNT in .env."
  value       = google_service_account.vertex_ml.email
}
