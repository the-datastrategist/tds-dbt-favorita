variable "project_id" {
  description = "GCP project that owns the Workload Identity Pool and CI service account."
  type        = string
}

variable "github_repository" {
  description = "GitHub repository allowed to authenticate, in owner/name form."
  type        = string

  validation {
    condition     = can(regex("^[^/]+/[^/]+$", var.github_repository))
    error_message = "github_repository must use the owner/name form."
  }
}

variable "pool_id" {
  description = "Workload Identity Pool ID."
  type        = string
  default     = "github-pool"
}

variable "provider_id" {
  description = "GitHub OIDC provider ID within the pool."
  type        = string
  default     = "github-provider"
}

variable "service_account_id" {
  description = "Account ID for the GitHub Actions Terraform plan identity."
  type        = string
  default     = "sa-github-terraform"
}

variable "project_roles" {
  description = "Read-only project roles required to refresh resources during terraform plan."
  type        = set(string)
  default = [
    "roles/iam.securityReviewer",
    "roles/viewer",
  ]
}

variable "state_bucket_name" {
  description = "Existing GCS backend bucket. Empty disables bucket IAM grants."
  type        = string
  default     = ""
}
