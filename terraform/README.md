# Terraform: GCP provisioning

Versioned replacement for the manual `scripts/setup_vertex_*.sh` bootstrap. Full design and
rationale: [`docs/specs/terraform_modules.md`](../docs/specs/terraform_modules.md).

```text
terraform/
  modules/
    gcp-apis/           # Enable required APIs
    artifact-registry/  # Docker repository
    iam-vertex-sa/       # SA + least-privilege role bindings
    github-wif/          # Repository-scoped GitHub OIDC + plan identity
    bigquery-datasets/   # raw + analytics datasets (not table schemas — see Non-goals below)
    gcs-buckets/          # raw, staging, models, mlflow
    cloud-scheduler/     # Optional HTTP jobs, disabled by default
  environments/
    dev/
    prod/
```

## New environment

```bash
cd terraform/environments/dev
cp terraform.tfvars.example terraform.tfvars   # fill in project_id, client_label, caller_member
terraform init -backend-config="bucket=<your-state-bucket>"
terraform plan
terraform apply
```

Each environment holds its own remote state (`backend.tf`, GCS bucket, versioning on). The
placeholder `CLIENT-terraform-state` bucket name must be overridden per client — either edit
`backend.tf` or pass `-backend-config="bucket=..."` at `init` time.

## Existing environment (adopt, don't recreate)

Clients provisioned via the shell scripts already have real resources. Import them instead of
letting `apply` try to recreate them — see the full "Migration plan" in
[`docs/specs/terraform_modules.md`](../docs/specs/terraform_modules.md#migration-plan-existing-environments)
for the `terraform import` sequence and the "zero diff before adopting" rule.

## Scope

- Table schemas (`vertex/ddl/vertex_bq_tables.sql`) stay owned by the DDL script / dbt, not
  Terraform — the `bigquery-datasets` module only manages dataset-level resources (location,
  labels). See the spec's Non-goals.
- WIF pool/provider resources are implemented by `modules/github-wif`; see the
  [Workload Identity Federation spec](../docs/specs/workload_identity_federation.md) for the
  bootstrap and GitHub environment configuration.
- `terraform apply` remains a manual, human-run command. CI runs `fmt`/`validate` and an
  authenticated dev `plan`, but has no infrastructure mutation roles and no apply step.

## Keyless GitHub Actions plan

For the supported guided path, authenticate locally and run:

```bash
gcloud auth application-default login
make bootstrap-check
make bootstrap-gcp
```

`bootstrap-check` is read-only and reports credential overrides, missing tools, project/API
access, state-bucket access, and GitHub authentication. `bootstrap-gcp` inventories known legacy
resources, imports matches into remote state, rejects any plan containing deletion, applies the
reviewed plan, configures the protected GitHub `dev` environment, and verifies a clean final plan.
It is safe to rerun. Use `python scripts/bootstrap_gcp.py bootstrap` without `--apply` to stop after
creating the reviewed plan.

1. Create the versioned dev state bucket before initializing this configuration.
2. Set `enable_github_wif`, `github_repository`, and `terraform_state_bucket` as shown in
   `environments/dev/terraform.tfvars.example`, then apply once with a trusted human identity.
3. Create a protected GitHub environment named `dev` and configure these environment variables:
   `GCP_DEV_PROJECT_ID`, `GCP_DEV_CLIENT_LABEL`, `GCP_DEV_CALLER_MEMBER`,
   `GCP_DEV_TF_STATE_BUCKET`, `GCP_DEV_WIF_PROVIDER`, and `GCP_DEV_WIF_SERVICE_ACCOUNT`. The final
   two values come from the Terraform outputs of the same names.

The `plan-dev` job does not run for pull requests from forks. Protect the `dev` environment with
required reviewers if plans should require approval. The CI service account has project viewer and
IAM security-reviewer roles plus object administration on the state bucket (needed for Terraform's
short-lived state lock); it has no roles that can apply infrastructure changes.
