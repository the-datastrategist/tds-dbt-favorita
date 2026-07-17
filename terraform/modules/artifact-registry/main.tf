resource "google_artifact_registry_repository" "vertex" {
  project       = var.project_id
  location      = var.region
  repository_id = var.repo_name
  format        = "DOCKER"
  description   = "tds-favorita Vertex training and pipeline image"
}
