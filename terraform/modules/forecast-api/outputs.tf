output "service_url" {
  value = var.enabled ? google_cloud_run_v2_service.api[0].uri : null
}

output "service_account_email" {
  value = var.enabled ? google_service_account.api[0].email : null
}
