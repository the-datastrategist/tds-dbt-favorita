terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.1"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 7.40"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
