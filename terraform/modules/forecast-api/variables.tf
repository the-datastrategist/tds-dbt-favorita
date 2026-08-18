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
variable "invoker_members" {
  description = "IAM members allowed to invoke the authenticated Cloud Run service."
  type        = set(string)
  default     = []
}
variable "min_instance_count" {
  type    = number
  default = 0
}
variable "max_instance_count" {
  type    = number
  default = 3
}
