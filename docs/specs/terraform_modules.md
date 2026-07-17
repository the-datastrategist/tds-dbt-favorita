{% docs spec_terraform_modules %}

# SPEC: Terraform modules for GCP provisioning

**Status:** Shipped
**Roadmap reference:** [`iac.md`](../iac.md#terraform-roadmap) — "Terraform roadmap"; [`client_rollout.md`](../client_rollout.md#post-rollout-weeks-58-optional) — "Terraform modules"

---

## Summary

GCP provisioning today is three imperative, idempotent-but-unreviewable shell scripts plus one Python DDL applicator, run by hand once per environment. This spec turns them into versioned Terraform modules per the structure already sketched (but not implemented) in [`iac.md`](../iac.md#terraform-roadmap), so client environments are code-reviewed, diffable, and reproducible across dev/prod.

## What exists today (being replaced/wrapped)

| Script | Does | Replaces |
|--------|------|----------|
| [`scripts/setup_vertex_artifact_registry.sh`](../../scripts/setup_vertex_artifact_registry.sh) | `gcloud services enable` (Artifact Registry, Vertex AI APIs) + create Docker repo | `gcp-apis` + `artifact-registry` modules |
| [`scripts/setup_vertex_service_account.sh`](../../scripts/setup_vertex_service_account.sh) | Create `sa-vertex-ml@...`, grant `aiplatform.user` / `storage.objectAdmin` / `bigquery.dataEditor` / `bigquery.jobUser`, grant `iam.serviceAccountUser` to the caller | `iam-vertex-sa` module |
| [`scripts/apply_vertex_bq_ddl.py`](../../scripts/apply_vertex_bq_ddl.py) (`make vertex-bq-ddl`) | Runs `vertex/ddl/vertex_bq_tables.sql` `CREATE TABLE IF NOT EXISTS` / `ALTER TABLE ADD COLUMN IF NOT EXISTS` statements | `bigquery-datasets` module (partially — see Non-goals) |
| *(manual)* | Creating GCS buckets (raw, staging, models, mlflow) per [`iac.md`](../iac.md#gcs-layout-recommended) | `gcs-buckets` module |
| *(manual)* | Cloud Scheduler + Cloud Run per [`iac.md`](../iac.md#scheduling-production) Pattern A | `cloud-scheduler` module |

## Goals

- Terraform module per resource type, matching the directory layout already committed to in `iac.md`:

```text
terraform/
  modules/
    gcp-apis/           # Enable required APIs
    bigquery-datasets/  # raw + analytics datasets
    gcs-buckets/         # raw, staging, models, mlflow
    artifact-registry/  # Docker repository
    iam-vertex-sa/       # SA + custom bucket/dataset bindings
    cloud-scheduler/     # Optional HTTP jobs
  environments/
    dev/
    prod/
```

- Variables map 1:1 to the `.env` contract already documented in `iac.md`'s "Variables to parameterize" table (`project_id`, `region`, `client_label`, `environment`, `dbt_dataset`, `raw_dataset`) — no new naming scheme to learn.
- `terraform plan`/`apply` is **idempotent against resources the shell scripts already created** (existing clients aren't forced to recreate their environment) — see Migration below.
- CI validates `terraform fmt` / `validate` / `plan` on every PR touching `terraform/`; `apply` stays a manual, human-gated step (this is real-money GCP infra, not something CI should auto-apply).

## Non-goals

- Managing the BigQuery **table schemas** themselves (`vertex/ddl/vertex_bq_tables.sql`) in Terraform. Table DDL changes frequently as new columns are added (e.g. the recent `favorita_model_explain` table) and is naturally expressed as SQL with `IF NOT EXISTS`/`ADD COLUMN IF NOT EXISTS` semantics that `apply_vertex_bq_ddl.py` already handles well. Terraform's `google_bigquery_table` resource would fight dbt/DDL-script ownership of schema. Scope Terraform to **datasets** (location, labels, retention), not tables.
- Workload Identity Federation resources (`google_iam_workload_identity_pool*`) — covered in the separate [WIF spec](workload_identity_federation.md); this spec's `iam-vertex-sa` module should be written so WIF bindings can be added later without restructuring it.
- Multi-cloud or non-GCP support.

## Implementation notes (as shipped)

All six modules and both environments below shipped as designed; two things deviated from the
letter of the spec, both because they're activities a sandboxed repo can't perform against a
real GCP org rather than design changes:

- **`terraform fmt`/`init -backend=false`/`validate` pass locally and in CI** (new
  `.github/workflows/terraform.yml`, matrixed over `dev`/`prod`) exactly as scoped — no live
  `plan`/`apply` in CI, per Goals and the CI section below. This required no `.tf` design changes,
  just building the modules to match `terraform validate`'s bar (valid HCL, resolvable module
  graph, no unset required variables without defaults).
- **The Migration plan (`terraform import` against a real client project) is documentation, not
  code** — it can't be executed or tested here since it requires an actual GCP project with
  resources the shell scripts already created. The plan as written in this doc is the
  deliverable; there was nothing to "ship" beyond writing it accurately, which the original spec
  already did.
- **`cloud-scheduler` ships as scaffolding only** (`enabled = false`, empty `jobs` map by
  default in both environments) exactly as the Design section calls for — no Cloud Run trigger
  service exists yet, so there's nothing real to point it at. This isn't a deviation, just
  confirming the "leave disabled" instruction was followed rather than skipped.
- **`bigquery-datasets`, `gcs-buckets`, `iam-vertex-sa`, `artifact-registry`, `gcp-apis` are wired
  into both `environments/dev` and `environments/prod`** with `depends_on = [module.gcp_apis]` on
  every module that needs an enabled API first — not called out explicitly in the original
  per-module Design snippets, but necessary for `terraform apply` ordering on a brand-new
  project (APIs must be enabled before e.g. `google_bigquery_dataset` can be created).
- `terraform/README.md` was added (not called for explicitly in the spec) as the one-paragraph
  "how do I actually run this" entry point, since the spec itself is a design doc, not a runbook.

Genuinely not done, as scoped by Non-goals and the CI section: no WIF pool/provider resources in
`iam-vertex-sa` (separate spec), and no live `plan`/`apply` — either locally against a real
project or in CI. Both require a real GCP org this repo doesn't have.

## Design

### Module: `gcp-apis`

```hcl
variable "project_id" { type = string }
variable "apis" {
  type    = list(string)
  default = ["artifactregistry.googleapis.com", "aiplatform.googleapis.com", "bigquery.googleapis.com", "storage.googleapis.com"]
}

resource "google_project_service" "enabled" {
  for_each = toset(var.apis)
  project  = var.project_id
  service  = each.value
  disable_on_destroy = false  # never disable a client's APIs on `terraform destroy`
}
```

### Module: `artifact-registry`

Direct translation of `setup_vertex_artifact_registry.sh`'s `gcloud artifacts repositories create`:

```hcl
resource "google_artifact_registry_repository" "vertex" {
  project       = var.project_id
  location      = var.region
  repository_id = var.repo_name          # default "vertex"
  format         = "DOCKER"
  description    = "tds-favorita Vertex training and pipeline image"
}
```

### Module: `iam-vertex-sa`

Translation of `setup_vertex_service_account.sh`, parameterized so the least-privilege role list stays a single source of truth (currently duplicated between `vertex/ops/README.md` and `iac.md`):

```hcl
variable "roles" {
  type    = list(string)
  default = ["roles/aiplatform.user", "roles/storage.objectAdmin", "roles/bigquery.dataEditor", "roles/bigquery.jobUser"]
}

resource "google_service_account" "vertex_ml" {
  project      = var.project_id
  account_id   = var.sa_id      # default "sa-vertex-ml"
  display_name = "Vertex AI pipeline/training jobs"
}

resource "google_project_iam_member" "vertex_ml_roles" {
  for_each = toset(var.roles)
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.vertex_ml.email}"
}

resource "google_service_account_iam_member" "caller_act_as" {
  service_account_id = google_service_account.vertex_ml.name
  role                = "roles/iam.serviceAccountUser"
  member              = var.caller_member   # "user:..." or "serviceAccount:..."
}
```

### Module: `bigquery-datasets`

```hcl
resource "google_bigquery_dataset" "raw" {
  project    = var.project_id
  dataset_id = var.raw_dataset   # default "raw_favorita"
  location   = var.bq_location   # default "US"
  labels     = { environment = var.environment, client = var.client_label }
}

resource "google_bigquery_dataset" "analytics" {
  project    = var.project_id
  dataset_id = var.dbt_dataset   # default "favorita"
  location   = var.bq_location
  labels     = { environment = var.environment, client = var.client_label }
}
```

### Module: `gcs-buckets`

One `google_storage_bucket` per bucket in `iac.md`'s GCS layout table (raw, staging, models, mlflow), each with `labels = { environment, client_label }` for the chargeback convention already used elsewhere (`GCP_CLIENT_LABEL`, `GCP_ENVIRONMENT`).

### Module: `cloud-scheduler`

Optional — only relevant once a client adopts `iac.md` Scheduling Pattern A (Cloud Scheduler → Cloud Run). Scaffolds a `google_cloud_scheduler_job` (HTTP target) per row in `iac.md`'s recommended cron table; leave `enabled = false` by default until a Cloud Run trigger service actually exists (not yet built — separate scope).

### Environments

`environments/dev` and `environments/prod` each wire the modules above with environment-specific `.tfvars`, and hold their own **remote state** (GCS backend bucket, one per environment, `versioning = true`):

```hcl
terraform {
  backend "gcs" {
    bucket = "CLIENT-terraform-state"
    prefix = "dev"   # or "prod"
  }
}
```

## Migration plan (existing environments)

Clients who provisioned via the shell scripts already have real resources. Terraform must **adopt**, not recreate:

1. Write modules first; do not run `apply` against an existing project yet.
2. `terraform import` each existing resource (service account, Artifact Registry repo, BigQuery datasets, GCS buckets) into the corresponding module's state address.
3. Run `terraform plan` and confirm **zero diff** before considering the module "adopted" — any diff at this stage means the module doesn't match reality yet (fix the module, not the real resource).
4. Only after a clean adopt-and-plan should `terraform apply` become the source of truth for that environment going forward; the shell scripts become dev-only / new-environment bootstrapping (or are retired once Terraform covers new-environment creation too).

## CI

New job in `.github/workflows/ci.yml` (or a dedicated `terraform.yml`), gated to `terraform/` path changes:

```yaml
terraform:
  name: Terraform fmt/validate/plan
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v6
    - uses: hashicorp/setup-terraform@v3
    - run: terraform -chdir=terraform/environments/dev fmt -check -recursive
    - run: terraform -chdir=terraform/environments/dev init -backend=false
    - run: terraform -chdir=terraform/environments/dev validate
    # No `plan`/`apply` in CI against real GCP — requires WIF-scoped CI credentials
    # (see workload_identity_federation.md) before this is safe to add.
```

`plan` against a live project requires CI to authenticate to GCP at all, which today it deliberately does not (CI uses a placeholder credentials file — see `.github/workflows/ci.yml`). Gate live `plan` in CI behind the [WIF spec](workload_identity_federation.md) landing first.

## Open questions

- Should `terraform/environments/prod` `apply` ever run from CI (with manual approval gate via GitHub Environments), or stay a local/operator-run command indefinitely? Recommend starting local-only; revisit once a client engagement needs multi-operator change control.
- One state bucket per client, or one shared bucket with per-client prefixes? Per-client bucket is cleaner for IAM isolation on client-managed GCP orgs; shared bucket is simpler for internal demo/dev. Decide per engagement type in `iac.md` once this ships.

## Related documents

- [Specs index](README.md)
- [IaC and GCP operations](../iac.md) — current manual runbook this codifies
- [Workload Identity Federation](workload_identity_federation.md) — prerequisite for CI `plan`/`apply`
- `vertex/ops/README.md` — IAM role source of truth

{% enddocs %}
