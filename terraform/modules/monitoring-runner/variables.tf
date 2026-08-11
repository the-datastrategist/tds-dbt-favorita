variable "project_id" { type = string }
variable "region" {
  type    = string
  default = "us-central1"
}
variable "enabled" {
  type    = bool
  default = false
}
variable "container_image" {
  description = "Immutable production image containing dbt and the monitoring evaluator."
  type        = string
  default     = ""
  validation {
    condition     = !var.enabled || var.container_image != ""
    error_message = "container_image is required when the monitoring runner is enabled."
  }
}
variable "service_account_email" { type = string }
variable "dbt_dataset" { type = string }
variable "raw_dataset" { type = string }
variable "schedule" {
  type    = string
  default = "15 * * * *"
}
variable "time_zone" {
  type    = string
  default = "Etc/UTC"
}
variable "job_name" {
  type    = string
  default = "forecast-monitoring-evaluator"
}
