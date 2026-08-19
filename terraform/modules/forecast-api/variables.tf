variable "project_id" { type = string }
variable "region" {
  type    = string
  default = "us-central1"
}
variable "enabled" {
  type    = bool
  default = false
}
variable "service_name" {
  type    = string
  default = "forecast-retrieval-api"
}
variable "container_image" {
  description = "Immutable production image containing vertex.api.app."
  type        = string
  default     = ""
  validation {
    condition     = !var.enabled || var.container_image != ""
    error_message = "container_image is required when the Forecast Retrieval API is enabled."
  }
}
variable "dbt_dataset" { type = string }
variable "enable_lifecycle_mutations" {
  description = "Enable append-only lifecycle endpoints and grant dataset write access. Restrict invoker_members to trusted operators when true."
  type        = bool
  default     = false
}
variable "enable_publication_webhook" {
  description = "Deliver signed publication events after successful API publication. Requires lifecycle mutations and both Secret Manager IDs."
  type        = bool
  default     = false
  validation {
    condition     = !var.enable_publication_webhook || var.enable_lifecycle_mutations
    error_message = "enable_publication_webhook requires enable_lifecycle_mutations."
  }
}
variable "publication_webhook_url_secret_id" {
  description = "Secret Manager secret ID containing the HTTPS webhook URL."
  type        = string
  default     = ""
  validation {
    condition     = !var.enable_publication_webhook || var.publication_webhook_url_secret_id != ""
    error_message = "publication_webhook_url_secret_id is required when webhook delivery is enabled."
  }
}
variable "publication_webhook_signing_secret_id" {
  description = "Secret Manager secret ID containing the HMAC signing secret."
  type        = string
  default     = ""
  validation {
    condition     = !var.enable_publication_webhook || var.publication_webhook_signing_secret_id != ""
    error_message = "publication_webhook_signing_secret_id is required when webhook delivery is enabled."
  }
}
variable "publication_webhook_name" {
  description = "Non-secret destination name used in delivery audit records."
  type        = string
  default     = "default"
}
variable "invoker_members" {
  description = "IAM members allowed to invoke the authenticated Cloud Run service."
  type        = set(string)
  default     = []
}
variable "enable_iap" {
  description = "Protect the Cloud Run ForecastLab UI and API with Identity-Aware Proxy."
  type        = bool
  default     = false
}
variable "iap_access_members" {
  description = "IAM members allowed through IAP to the ForecastLab UI and API."
  type        = set(string)
  default     = []
  validation {
    condition     = var.enable_iap || length(var.iap_access_members) == 0
    error_message = "iap_access_members requires enable_iap = true."
  }
}
variable "min_instance_count" {
  type    = number
  default = 0
}
variable "max_instance_count" {
  type    = number
  default = 3
}
