resource "google_cloud_run_v2_job" "monitoring" {
  count = var.enabled ? 1 : 0

  project             = var.project_id
  location            = var.region
  name                = var.job_name
  deletion_protection = false

  template {
    template {
      service_account = var.service_account_email
      timeout         = "1800s"
      max_retries     = 1

      containers {
        image   = var.container_image
        command = ["/bin/sh"]
        args = [
          "-c",
          "dbt build --project-dir dbt --profiles-dir dbt/profiles --target prod --selector forecast_monitoring && python scripts/evaluate_monitoring_alerts.py --project-id ${var.project_id} --table-prefix ${var.project_id}.${var.dbt_dataset}",
        ]

        env {
          name  = "GOOGLE_PROJECT_ID"
          value = var.project_id
        }
        env {
          name  = "DBT_DATASET"
          value = var.dbt_dataset
        }
        env {
          name  = "BQ_RAW_DATASET"
          value = var.raw_dataset
        }
        env {
          name  = "DBT_PROFILES_DIR"
          value = "/app/dbt/profiles"
        }
        env {
          name = "FORECAST_SLACK_WEBHOOK_URL"
          value_source {
            secret_key_ref {
              secret  = var.slack_webhook_secret_id
              version = "latest"
            }
          }
        }

        resources {
          limits = {
            cpu    = "1"
            memory = "1Gi"
          }
        }
      }
    }
  }

  depends_on = [google_secret_manager_secret_iam_member.slack_webhook_accessor]
}

resource "google_secret_manager_secret_iam_member" "slack_webhook_accessor" {
  count = var.enabled ? 1 : 0

  project   = var.project_id
  secret_id = var.slack_webhook_secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.service_account_email}"
}

resource "google_cloud_run_v2_job_iam_member" "scheduler_invoker" {
  count = var.enabled ? 1 : 0

  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_job.monitoring[0].name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${var.service_account_email}"
}

resource "google_cloud_scheduler_job" "monitoring" {
  count = var.enabled ? 1 : 0

  project   = var.project_id
  region    = var.region
  name      = "${var.job_name}-schedule"
  schedule  = var.schedule
  time_zone = var.time_zone

  retry_config {
    retry_count          = 2
    min_backoff_duration = "30s"
    max_backoff_duration = "300s"
  }

  http_target {
    uri         = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/${var.job_name}:run"
    http_method = "POST"

    oauth_token {
      service_account_email = var.service_account_email
      scope                 = "https://www.googleapis.com/auth/cloud-platform"
    }
  }

  depends_on = [
    google_cloud_run_v2_job_iam_member.scheduler_invoker,
    google_secret_manager_secret_iam_member.slack_webhook_accessor,
  ]
}
