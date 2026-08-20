resource "google_service_account" "api" {
  count = var.enabled ? 1 : 0

  project      = var.project_id
  account_id   = "forecast-retrieval-api"
  display_name = "Forecast Retrieval API"
}

resource "google_project_service_identity" "iap" {
  provider = google-beta
  count    = var.enabled && var.enable_iap ? 1 : 0

  project = var.project_id
  service = "iap.googleapis.com"
}

resource "google_project_iam_member" "bigquery_job_user" {
  count = var.enabled ? 1 : 0

  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.api[0].email}"
}

moved {
  from = google_bigquery_dataset_iam_member.forecast_reader
  to   = google_bigquery_dataset_iam_member.forecast_dataset_access
}

resource "google_bigquery_dataset_iam_member" "forecast_dataset_access" {
  count = var.enabled ? 1 : 0

  project    = var.project_id
  dataset_id = var.dbt_dataset
  role       = var.enable_lifecycle_mutations ? "roles/bigquery.dataEditor" : "roles/bigquery.dataViewer"
  member     = "serviceAccount:${google_service_account.api[0].email}"
}

resource "google_cloud_run_v2_service" "api" {
  count = var.enabled ? 1 : 0

  project             = var.project_id
  location            = var.region
  name                = var.service_name
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = true
  iap_enabled         = var.enable_iap

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
      env {
        name  = "FORECAST_API_MUTATIONS_ENABLED"
        value = tostring(var.enable_lifecycle_mutations)
      }
      env {
        name  = "FORECAST_API_AUTHORIZATION_ENABLED"
        value = tostring(var.enable_iap)
      }
      env {
        name = "FORECAST_API_ROLE_MEMBERS_JSON"
        value = jsonencode({
          for role, members in var.lifecycle_role_members : role => sort(tolist(members))
        })
      }
      env {
        name  = "FORECAST_PUBLICATION_WEBHOOK_NAME"
        value = var.publication_webhook_name
      }
      dynamic "env" {
        for_each = var.enable_publication_webhook ? [1] : []
        content {
          name = "FORECAST_PUBLICATION_WEBHOOK_URL"
          value_source {
            secret_key_ref {
              secret  = var.publication_webhook_url_secret_id
              version = "latest"
            }
          }
        }
      }
      dynamic "env" {
        for_each = var.enable_publication_webhook ? [1] : []
        content {
          name = "FORECAST_PUBLICATION_WEBHOOK_SIGNING_SECRET"
          value_source {
            secret_key_ref {
              secret  = var.publication_webhook_signing_secret_id
              version = "latest"
            }
          }
        }
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
    google_bigquery_dataset_iam_member.forecast_dataset_access,
    google_secret_manager_secret_iam_member.webhook_url_accessor,
    google_secret_manager_secret_iam_member.webhook_signing_accessor,
  ]
}

resource "google_secret_manager_secret_iam_member" "webhook_url_accessor" {
  count = var.enabled && var.enable_publication_webhook ? 1 : 0

  project   = var.project_id
  secret_id = var.publication_webhook_url_secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.api[0].email}"
}

resource "google_secret_manager_secret_iam_member" "webhook_signing_accessor" {
  count = var.enabled && var.enable_publication_webhook ? 1 : 0

  project   = var.project_id
  secret_id = var.publication_webhook_signing_secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.api[0].email}"
}

resource "google_cloud_run_v2_service_iam_member" "invoker" {
  for_each = var.enabled ? var.invoker_members : toset([])

  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.api[0].name
  role     = "roles/run.invoker"
  member   = each.value
}

resource "google_cloud_run_v2_service_iam_member" "iap_invoker" {
  count = var.enabled && var.enable_iap ? 1 : 0

  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.api[0].name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_project_service_identity.iap[0].email}"
}

resource "google_iap_web_cloud_run_service_iam_member" "forecastlab_user" {
  for_each = var.enabled && var.enable_iap ? var.iap_access_members : toset([])

  project                = var.project_id
  location               = var.region
  cloud_run_service_name = google_cloud_run_v2_service.api[0].name
  role                   = "roles/iap.httpsResourceAccessor"
  member                 = each.value
}
