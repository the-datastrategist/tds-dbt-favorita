resource "google_cloud_scheduler_job" "jobs" {
  for_each = var.enabled ? var.jobs : {}

  project  = var.project_id
  region   = var.region
  name     = each.key
  schedule = each.value.schedule

  http_target {
    uri         = each.value.uri
    http_method = each.value.http_method
  }
}
