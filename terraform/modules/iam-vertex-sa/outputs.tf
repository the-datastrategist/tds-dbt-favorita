output "email" {
  description = "Set as VERTEX_PIPELINE_SERVICE_ACCOUNT in .env."
  value       = google_service_account.vertex_ml.email
}

output "prediction_email" {
  description = "Email of the read-only-artifact prediction service account."
  value       = google_service_account.vertex_prediction.email
}
