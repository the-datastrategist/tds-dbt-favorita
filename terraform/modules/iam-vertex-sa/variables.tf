variable "project_id" {
  type = string
}

variable "sa_id" {
  description = "Service account ID (before @project.iam.gserviceaccount.com). Maps to VERTEX_PIPELINE_SERVICE_ACCOUNT."
  type        = string
  default     = "sa-vertex-ml"
}

variable "roles" {
  description = "Least-privilege roles granted to the Vertex pipeline service account. Keep this the single source of truth instead of vertex/ops/README.md's duplicated list."
  type        = list(string)
  default = [
    "roles/aiplatform.user",
    "roles/storage.objectAdmin",
    "roles/bigquery.dataEditor",
    "roles/bigquery.jobUser",
  ]
}

variable "caller_member" {
  description = <<-EOT
    Identity allowed to "act as" the Vertex pipeline service account when submitting Custom
    Jobs / PipelineJobs, e.g. "user:you@example.com" or
    "serviceAccount:ci@project.iam.gserviceaccount.com". Equivalent to CALLER_ACCOUNT in
    scripts/setup_vertex_service_account.sh. WIF-federated CI principals (once
    docs/specs/workload_identity_federation.md ships) also go here.
  EOT
  type        = string
}
