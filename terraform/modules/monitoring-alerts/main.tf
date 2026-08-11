resource "google_logging_metric" "failed_forecast_jobs" {
  count = var.enabled ? 1 : 0

  project = var.project_id
  name    = "forecast_failed_jobs"
  filter  = <<-EOT
    severity>=ERROR AND (
      resource.type="aiplatform.googleapis.com/CustomJob" OR
      resource.type="cloud_run_job" OR
      resource.type="cloud_scheduler_job"
    )
  EOT

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"
  }
}

resource "google_monitoring_alert_policy" "failed_forecast_jobs" {
  count = var.enabled ? 1 : 0

  project      = var.project_id
  display_name = "Forecast platform failed jobs"
  combiner     = "OR"
  enabled      = true

  conditions {
    display_name = "At least one error-level forecast job log"

    condition_threshold {
      filter          = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.failed_forecast_jobs[0].name}\" AND resource.type=\"global\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"

      aggregations {
        alignment_period   = var.alignment_period
        per_series_aligner = "ALIGN_SUM"
      }
    }
  }

  notification_channels = var.notification_channel_ids

  documentation {
    content   = "A forecast-platform job emitted an error log. Follow docs/monitoring_and_slos.md and inspect the latest pipeline-health row."
    mime_type = "text/markdown"
  }
}
