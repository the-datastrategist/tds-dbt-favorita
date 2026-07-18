output "workload_identity_provider" {
  description = "Full provider resource name for google-github-actions/auth."
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "service_account_email" {
  description = "Service account impersonated by GitHub Actions."
  value       = google_service_account.github_terraform.email
}
