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

variable "monitoring_slack_webhook_secret_id" {
  description = "Secret Manager secret ID containing the Slack incoming-webhook URL."
  type        = string
  default     = ""
}

variable "monitoring_runner_schedule" {
  description = "UTC cron schedule for monitoring evaluation."
  type        = string
  default     = "15 * * * *"
}

variable "enable_forecast_api" {
  description = "Create the authenticated Forecast Operations API."
  type        = bool
  default     = false
}

variable "enable_forecast_api_mutations" {
  description = "Enable lifecycle writes; use only with operator-only forecast_api_invoker_members."
  type        = bool
  default     = false
}

variable "enable_forecast_publication_webhook" {
  description = "Enable signed outbound publication webhooks."
  type        = bool
  default     = false
}

variable "forecast_publication_webhook_url_secret_id" {
  description = "Secret Manager secret ID containing the publication webhook URL."
  type        = string
  default     = ""
}

variable "forecast_publication_webhook_signing_secret_id" {
  description = "Secret Manager secret ID containing the publication webhook HMAC secret."
  type        = string
  default     = ""
}

variable "forecast_publication_webhook_name" {
  description = "Non-secret webhook destination name used in delivery audit records."
  type        = string
  default     = "default"
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

variable "enable_forecastlab_iap" {
  description = "Protect the same-origin ForecastLab UI and API with Identity-Aware Proxy."
  type        = bool
  default     = false
}

variable "forecastlab_iap_access_members" {
  description = "IAM members allowed to access ForecastLab through IAP."
  type        = set(string)
  default     = []
}

variable "forecastlab_lifecycle_role_members" {
  description = "IAP-authenticated users assigned ForecastLab lifecycle roles."
  type        = map(set(string))
  default     = {}
}

variable "forecast_api_min_instances" {
  description = "Minimum warm Cloud Run instances for the Forecast Retrieval API."
  type        = number
  default     = 0
}

variable "forecast_api_max_instances" {
  description = "Maximum Cloud Run instances for the Forecast Retrieval API."
  type        = number
  default     = 10
}
