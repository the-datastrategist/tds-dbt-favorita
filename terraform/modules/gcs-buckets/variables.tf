variable "project_id" {
  type = string
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "client_label" {
  description = "Bucket name prefix, e.g. \"acme-corp\" -> acme-corp-raw, acme-corp-vertex-staging, acme-corp-vertex-models. Maps to GCP_CLIENT_LABEL."
  type        = string
}

variable "environment" {
  description = "Maps to GCP_ENVIRONMENT. Applied as a bucket label for chargeback."
  type        = string
}

variable "enable_mlflow_bucket" {
  description = "Set false if MLFLOW_TRACKING_URI stays local (file:./mlruns) for this environment."
  type        = bool
  default     = true
}

variable "force_destroy" {
  description = "Allow `terraform destroy` to delete non-empty buckets. Keep false in prod."
  type        = bool
  default     = false
}
