output "failed_forecast_jobs_alert_policy_id" {
  value = var.enabled ? google_monitoring_alert_policy.failed_forecast_jobs[0].id : null
}
