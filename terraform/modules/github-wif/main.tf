resource "google_service_account" "github_terraform" {
  project      = var.project_id
  account_id   = var.service_account_id
  display_name = "GitHub Actions Terraform plan"
  description  = "Keyless, plan-only identity for ${var.github_repository}."
}

resource "google_iam_workload_identity_pool" "github" {
  project                   = var.project_id
  workload_identity_pool_id = var.pool_id
  display_name              = "GitHub Actions"
  description               = "OIDC identities trusted from ${var.github_repository}."
}

resource "google_iam_workload_identity_pool_provider" "github" {
  project                            = var.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = var.provider_id
  display_name                       = "GitHub repository provider"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }

  # The IAM principalSet below is repository-scoped too; this condition rejects tokens from
  # every other repository before they reach service-account impersonation.
  attribute_condition = "assertion.repository == '${var.github_repository}'"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "github_wif" {
  service_account_id = google_service_account.github_terraform.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repository}"
}

resource "google_project_iam_member" "plan_reader" {
  for_each = var.project_roles

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.github_terraform.email}"
}

# Terraform's GCS backend writes a short-lived lock object even for plan. Restrict that write
# permission to the state bucket; the CI identity has no infrastructure mutation roles.
resource "google_storage_bucket_iam_member" "state" {
  count = var.state_bucket_name == "" ? 0 : 1

  bucket = var.state_bucket_name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.github_terraform.email}"
}
