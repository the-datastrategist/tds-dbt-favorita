resource "google_project_service" "enabled" {
  for_each = toset(var.apis)

  project = var.project_id
  service = each.value

  # Never disable a client's APIs on `terraform destroy` — this repo doesn't own the decision to
  # turn off billing-relevant APIs for a project that may have other consumers.
  disable_on_destroy = false
}
