variable "project_id" {
  type = string
}

variable "enabled" {
  description = "Create forecast-platform log metrics and alert policies. Disabled by default."
  type        = bool
  default     = false
}

variable "notification_channel_ids" {
  description = "Existing Cloud Monitoring notification channel resource IDs."
  type        = list(string)
  default     = []
}

variable "alignment_period" {
  description = "Evaluation period for failed forecast job alerts."
  type        = string
  default     = "300s"
}
