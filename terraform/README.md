# Terraform: GCP provisioning

Versioned replacement for the manual `scripts/setup_vertex_*.sh` bootstrap. Full design and
rationale: [`docs/specs/terraform_modules.md`](../docs/specs/terraform_modules.md).

```text
terraform/
  modules/
    gcp-apis/           # Enable required APIs
    artifact-registry/  # Docker repository
    iam-vertex-sa/       # SA + least-privilege role bindings
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
- WIF pool/provider resources live in the separate
  [Workload Identity Federation spec](../docs/specs/workload_identity_federation.md); `iam-vertex-sa`
  is written so those bindings can be added later without restructuring it.
- `terraform apply` is a manual, human-run command — CI only runs `fmt`/`validate`
  (`.github/workflows/terraform.yml`), never `plan`/`apply` against a live project.
