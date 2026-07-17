output "repository_id" {
  value = google_artifact_registry_repository.vertex.repository_id
}

output "repository_url" {
  description = "Push target for `make vertex-docker-push` / `gcloud auth configure-docker`."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.vertex.repository_id}"
}
