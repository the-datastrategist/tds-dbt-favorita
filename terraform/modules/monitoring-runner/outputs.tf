output "job_name" {
  value = var.enabled ? google_cloud_run_v2_job.monitoring[0].name : null
}

output "scheduler_job_name" {
  value = var.enabled ? google_cloud_scheduler_job.monitoring[0].name : null
}
