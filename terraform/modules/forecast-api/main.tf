resource "google_service_account" "api" {
  count = var.enabled ? 1 : 0

  project      = var.project_id
  account_id   = "forecast-retrieval-api"
  display_name = "Forecast Retrieval API"
}

resource "google_project_iam_member" "bigquery_job_user" {
  count = var.enabled ? 1 : 0

  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.api[0].email}"
}

resource "google_bigquery_dataset_iam_member" "forecast_reader" {
  count = var.enabled ? 1 : 0

  project    = var.project_id
  dataset_id = var.dbt_dataset
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${google_service_account.api[0].email}"
}

resource "google_cloud_run_v2_service" "api" {
  count = var.enabled ? 1 : 0

  project             = var.project_id
  location            = var.region
  name                = var.service_name
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account = google_service_account.api[0].email

    scaling {
      min_instance_count = var.min_instance_count
      max_instance_count = var.max_instance_count
    }

    containers {
      image   = var.container_image
      command = ["uvicorn"]
      args    = ["vertex.api.app:app", "--host", "0.0.0.0", "--port", "8080"]

      ports {
        container_port = 8080
      }

      env {
        name  = "GOOGLE_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "DBT_DATASET"
        value = var.dbt_dataset
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }
    }
  }

  depends_on = [
    google_project_iam_member.bigquery_job_user,
    google_bigquery_dataset_iam_member.forecast_reader,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "invoker" {
  for_each = var.enabled ? var.invoker_members : toset([])

  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.api[0].name
  role     = "roles/run.invoker"
  member   = each.value
}
