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
  default     = "US"
}

variable "environment" {
  description = "Maps to GCP_ENVIRONMENT."
  type        = string
  default     = "dev"
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

variable "enable_github_wif" {
  description = "Create repository-scoped GitHub OIDC trust and its Terraform plan identity."
  type        = bool
  default     = false
}

variable "github_repository" {
  description = "Repository trusted by WIF, in owner/name form. Required when enable_github_wif is true."
  type        = string
  default     = "placeholder/placeholder"

  validation {
    condition     = !var.enable_github_wif || var.github_repository != "placeholder/placeholder"
    error_message = "Set github_repository to the real owner/name when enable_github_wif is true."
  }
}

variable "terraform_state_bucket" {
  description = "Existing dev GCS backend bucket granted to the plan-only CI identity."
  type        = string
  default     = ""

  validation {
    condition     = !var.enable_github_wif || var.terraform_state_bucket != ""
    error_message = "Set terraform_state_bucket when enable_github_wif is true."
  }
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

variable "enable_monitoring_runner" {
  description = "Create the scheduled Cloud Run monitoring evaluator."
  type        = bool
  default     = false
}

variable "monitoring_runner_image" {
  description = "Immutable production image URI for the monitoring Cloud Run Job."
  type        = string
  default     = ""
}

variable "monitoring_runner_schedule" {
  description = "UTC cron schedule for monitoring evaluation."
  type        = string
  default     = "15 * * * *"
}

variable "enable_forecast_api" {
  description = "Create the authenticated read-only Forecast Retrieval API."
  type        = bool
  default     = false
}

variable "forecast_api_image" {
  description = "Immutable production image URI for the Forecast Retrieval API."
  type        = string
  default     = ""
}

variable "forecast_api_invoker_members" {
  description = "IAM members allowed to invoke the Forecast Retrieval API."
  type        = set(string)
  default     = []
}

variable "forecast_api_max_instances" {
  description = "Maximum Cloud Run instances for the Forecast Retrieval API."
  type        = number
  default     = 3
}
