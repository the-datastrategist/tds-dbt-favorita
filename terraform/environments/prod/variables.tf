# Variable names map 1:1 to docs/iac.md's "Variables to parameterize" table / the .env contract
# — no new naming scheme to learn.

variable "project_id" {
  description = "Maps to GOOGLE_PROJECT_ID."
  type        = string
}

variable "region" {
  description = "Maps to VERTEX_AI_REGION."
  type        = string
  default     = "us-central1"
}

variable "bucket_location" {
  description = "GCS bucket location, separate from the Vertex compute region."
  type        = string
  default     = "us-central1"
}

variable "environment" {
  description = "Maps to GCP_ENVIRONMENT."
  type        = string
  default     = "prod"
}

variable "client_label" {
  description = "Maps to GCP_CLIENT_LABEL."
  type        = string
}

variable "dbt_dataset" {
  description = "Maps to DBT_DATASET."
  type        = string
  default     = "favorita"
}

variable "raw_dataset" {
  description = "Maps to BQ_RAW_DATASET."
  type        = string
  default     = "raw_favorita"
}

variable "repo_name" {
  description = "Maps to ARTIFACT_REGISTRY_REPO."
  type        = string
  default     = "vertex"
}

variable "sa_id" {
  description = "Service account ID before the @project.iam.gserviceaccount.com suffix."
  type        = string
  default     = "sa-vertex-ml"
}

variable "caller_member" {
  description = "Identity allowed to act as the Vertex service account, e.g. \"user:you@example.com\". See modules/iam-vertex-sa."
  type        = string
}

variable "enable_monitoring_alerts" {
  description = "Create opt-in Cloud Monitoring policies for failed forecast jobs."
  type        = bool
  default     = false
}

variable "monitoring_notification_channel_ids" {
  description = "Existing Cloud Monitoring notification channel resource IDs."
  type        = list(string)
  default     = []
}
