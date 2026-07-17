resource "google_service_account" "vertex_ml" {
  project      = var.project_id
  account_id   = var.sa_id
  display_name = "Vertex AI pipeline/training jobs"
}

resource "google_project_iam_member" "vertex_ml_roles" {
  for_each = toset(var.roles)

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.vertex_ml.email}"
}

resource "google_service_account_iam_member" "caller_act_as" {
  service_account_id = google_service_account.vertex_ml.name
  role               = "roles/iam.serviceAccountUser"
  member             = var.caller_member
}
