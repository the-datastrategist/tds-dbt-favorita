# GCP and GitHub bootstrap

Use this guide to provision or adopt the platform infrastructure and configure keyless GitHub
Actions authentication. The bootstrap is safe to rerun and never stores a GCP service-account key
in GitHub.

After completing this infrastructure guide, continue with
[Generate your first forecast](first_forecast.md) to validate the platform contracts, build
features, run a model, and inspect canonical output.

## Before you begin

Install Google Cloud CLI (`gcloud`, `bq`, and `gcloud storage`), Terraform 1.5+, GitHub CLI (`gh`),
and Python 3.11+. You also need:

- A billing-enabled GCP project
- Temporary permission to manage APIs, service accounts, IAM, WIF, BigQuery, Cloud Storage, and
  Artifact Registry during bootstrap
- Administrator access to the target GitHub repository
- A versioned GCS bucket for Terraform state

The broad bootstrap permissions belong to the human installer only. GitHub receives a separate,
limited service account after setup.

## 1. Clone and enter the repository

```bash
git clone https://github.com/YOUR_ORG/YOUR_REPOSITORY.git
cd YOUR_REPOSITORY
```

## 2. Authenticate locally

```bash
gcloud auth login
gcloud auth application-default login
gh auth login
```

Application Default Credentials (ADC) authenticate Terraform on your workstation. They do not
authenticate GitHub Actions; the bootstrap configures Workload Identity Federation for that.

If your shell loaded `.env`, it may set `GOOGLE_APPLICATION_CREDENTIALS`. The supported Make
targets automatically remove that override for bootstrap commands.

## 3. Create the state bucket

Skip creation if your organization already provides a Terraform state bucket.

```bash
gcloud storage buckets create gs://YOUR_STATE_BUCKET \
  --project=YOUR_PROJECT_ID \
  --location=US \
  --uniform-bucket-level-access

gcloud storage buckets update gs://YOUR_STATE_BUCKET --versioning
```

Bucket names are globally unique. Use only the bucket name, without `gs://`, in Terraform inputs.

## 4. Configure the dev environment

```bash
cp terraform/environments/dev/terraform.tfvars.example \
  terraform/environments/dev/terraform.tfvars
```

Set at least:

```hcl
project_id      = "YOUR_PROJECT_ID"
client_label    = "YOUR_CLIENT_LABEL"
caller_member   = "user:YOUR_GOOGLE_EMAIL"

enable_github_wif      = true
github_repository      = "YOUR_ORG/YOUR_REPOSITORY"
terraform_state_bucket = "YOUR_STATE_BUCKET"
```

Initialize the backend once:

```bash
terraform -chdir=terraform/environments/dev init -reconfigure \
  -backend-config="bucket=YOUR_STATE_BUCKET"
```

Do not commit `terraform.tfvars`, Terraform plans, credentials, or generated GitHub credentials.

## 5. Run the preflight

```bash
make bootstrap-check
```

This command makes no changes. It checks local tools, ADC, project and Service Usage access, the
state bucket, and GitHub authentication. Resolve every failure before continuing.

## 6. Bootstrap or adopt the platform

Preview without applying:

```bash
env -u GOOGLE_APPLICATION_CREDENTIALS -u GOOGLE_CREDENTIALS \
  python scripts/bootstrap_gcp.py bootstrap
```

Run the supported end-to-end setup:

```bash
make bootstrap-gcp
```

The command:

1. Discovers known service accounts, datasets, buckets, Artifact Registry, and WIF resources.
2. Imports existing matches into Terraform state instead of recreating them.
3. Creates a plan and refuses any deletion or replacement.
4. Applies the safe plan.
5. Creates or updates the GitHub `dev` environment variables.
6. Requires a clean final Terraform plan.

New resources are created when missing. Existing matching resources are adopted. Material
conflicts stop the process for human review.

## 7. Verify GitHub authentication

Commit and push the repository changes, then run **WIF smoke test** from GitHub Actions. It verifies
federated GCP authentication, Terraform drift, and dbt authentication and compilation.

The smoke workflow uses the `wif` output in `dbt/profiles/profiles.yml`. That target selects
BigQuery's `oauth` method so dbt consumes the external-account ADC file created by
`google-github-actions/auth`; it must not use the local `dev` target, which intentionally expects
a service-account key file.

The reference environment's OIDC exchange, federated project access, and keyless Terraform plan
were accepted on 2026-07-18 in GitHub Actions run
[`29648312277`](https://github.com/the-datastrategist/tds-dbt-favorita/actions/runs/29648312277).
That run exposed the former dbt key-file profile mismatch. After committing the dedicated `wif`
target, rerun the workflow and replace this note with the final fully green run URL.

The GitHub `dev` environment should contain:

| Variable | Purpose |
|---|---|
| `GCP_DEV_PROJECT_ID` | Target GCP project |
| `GCP_DEV_CLIENT_LABEL` | Resource naming prefix |
| `GCP_DEV_CALLER_MEMBER` | Human allowed to submit Vertex jobs |
| `GCP_DEV_TF_STATE_BUCKET` | Remote Terraform state bucket |
| `GCP_DEV_WIF_PROVIDER` | Full GitHub OIDC provider name |
| `GCP_DEV_WIF_SERVICE_ACCOUNT` | Keyless GitHub Terraform identity |

No service-account JSON secret is required.

## Common failures

### Permission denied while listing project services

The bootstrap identity needs `roles/serviceusage.serviceUsageAdmin`. Confirm ADC was created with
the intended account.

### Terraform uses the wrong identity

```bash
printenv GOOGLE_APPLICATION_CREDENTIALS
```

Use the Make targets, which unset this override, or explicitly unset it before Terraform.

### A resource already exists

Run `make bootstrap-gcp` instead of direct `terraform apply`. The guided command discovers and
imports supported legacy resources before planning.

### The plan contains a delete or replacement

The bootstrap stops automatically. Do not bypass this guard. Reconcile the existing resource and
configuration intentionally.

### GitHub WIF authentication fails

Confirm the workflow has `id-token: write`, runs after checkout, uses the `dev` environment, and
that `github_repository` matches the repository exactly, including case.

### dbt asks you to log into GCP in the smoke workflow

Confirm every smoke-workflow dbt command includes `--target wif`. The `dev` and `prod` targets use
`method: service-account` for local key-file compatibility; the `wif` target uses ADC and accepts
the external-account credential generated from GitHub OIDC.

## Local runtime credentials

WIF is for GitHub Actions. Docker-based local dbt and Vertex commands may still use the gitignored
service-account file configured in `.env`. Organizations that prohibit keys can use
service-account impersonation with ADC instead.

For details, see [Terraform provisioning](../terraform/README.md) and the
[Workload Identity Federation specification](specs/workload_identity_federation.md).
