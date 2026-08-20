variable "project_id" {
  type = string
}

variable "bq_location" {
  type    = string
  default = "US"
}

variable "raw_dataset" {
  description = "Maps to BQ_RAW_DATASET."
  type        = string
}

variable "dbt_dataset" {
  description = "Maps to DBT_DATASET."
  type        = string
}

variable "environment" {
  description = "Maps to GCP_ENVIRONMENT. Applied as a dataset label for chargeback."
  type        = string
}

variable "client_label" {
  description = "Maps to GCP_CLIENT_LABEL. Applied as a dataset label for chargeback."
  type        = string
}
