variable "project_id" {
  type = string
}

variable "region" {
  description = "Maps to VERTEX_AI_REGION."
  type        = string
  default     = "us-central1"
}

variable "repo_name" {
  description = "Artifact Registry repository ID. Maps to ARTIFACT_REGISTRY_REPO."
  type        = string
  default     = "vertex"
}
