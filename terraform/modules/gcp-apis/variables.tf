variable "project_id" {
  description = "GCP project ID to enable APIs in."
  type        = string
}

variable "apis" {
  description = "APIs required by the Vertex AI + BigQuery ML stack. Translation of scripts/setup_vertex_artifact_registry.sh's `gcloud services enable`."
  type        = list(string)
  default = [
    "artifactregistry.googleapis.com",
    "aiplatform.googleapis.com",
    "bigquery.googleapis.com",
    "storage.googleapis.com",
  ]
}
