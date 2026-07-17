# One remote-state bucket per environment (versioning enabled), per
# docs/specs/terraform_modules.md "Environments". Override the bucket at init time if a client's
# state bucket doesn't follow the CLIENT-terraform-state convention:
#   terraform init -backend-config="bucket=my-actual-state-bucket"
terraform {
  backend "gcs" {
    bucket = "CLIENT-terraform-state"
    prefix = "dev"
  }
}
