variable "project_id" {
  type = string
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "enabled" {
  description = "Master switch. Leave false until a Cloud Run trigger service actually exists (docs/iac.md Scheduling Pattern A) — this module is scaffolding, not yet wired to a real target."
  type        = bool
  default     = false
}

variable "jobs" {
  description = <<-EOT
    HTTP Cloud Scheduler jobs, keyed by job name. Each should target a Cloud Run trigger service
    running the corresponding entrypoint — see docs/iac.md "Scheduling (production)" recommended
    cron table (dbt features, Vertex train, full ML pipeline).
  EOT
  type = map(object({
    schedule    = string
    uri         = string
    http_method = optional(string, "POST")
  }))
  default = {}
}
