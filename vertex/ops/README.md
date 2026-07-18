# Vertex operations (GCP)

Runbook for productionizing this template in a client GCP organization.

## IAM (least privilege)

Create a **Vertex AI service account** per environment (e.g. `sa-vertex-ml@PROJECT.iam.gserviceaccount.com`) with:

| Role | Purpose |
|------|---------|
| `roles/aiplatform.user` | Submit Custom Jobs and PipelineJobs |
| `roles/storage.objectUser` | Staging, model, and MLflow buckets (bucket-level only) |
| `roles/bigquery.dataEditor` | Raw and analytics datasets (dataset-level only) |
| `roles/bigquery.jobUser` | Run queries for training data |

The Terraform modules grant Storage and BigQuery data roles only on the named buckets and
datasets. Do not grant either data-plane role at project scope.

Terraform also creates a separate prediction identity. Set its output as
`VERTEX_PREDICTION_SERVICE_ACCOUNT`; it receives `storage.objectViewer` on the model bucket,
not artifact write access. Standalone `--step predict` submissions select it automatically.
Multi-step PipelineJobs still use one pipeline identity for every component, so workloads that
require strict per-step isolation should submit train and predict as separate Custom Jobs.

Set in `.env`:

```bash
VERTEX_PIPELINE_SERVICE_ACCOUNT=sa-vertex-ml@PROJECT.iam.gserviceaccount.com
VERTEX_PREDICTION_SERVICE_ACCOUNT=sa-vertex-ml-predict@PROJECT.iam.gserviceaccount.com
```

Custom Jobs and PipelineJobs use this account when set.

**Keep this identity distinct from the local/orchestrator identity** the `ml-pipeline`
container runs as (`GOOGLE_APPLICATION_CREDENTIALS`). The local identity still needs to write
BigQuery/GCS directly for dbt and raw ingestion (and, for local iteration only, `VERTEX_MODE=docker`
training runs) — but every *scheduled* Prefect deployment in `prefect.yaml` uses
`vertex_mode: vertex`, so production training/predict/optimize only ever runs as `sa-vertex-ml`.
See [docs/iac.md](../../docs/iac.md#local--orchestrator-identity-defense-in-depth) for the
recommended role split and its dataset-sharing caveat.

Provision this (and the rest of this runbook's resources) via versioned Terraform instead of
by hand — see [`terraform/README.md`](../../terraform/README.md) and
[`docs/specs/terraform_modules.md`](../../docs/specs/terraform_modules.md). The
`scripts/setup_vertex_*.sh` shell scripts remain for quick bootstrap or as the import source for
environments Terraform is adopting.

## GCS layout (recommended)

```text
gs://CLIENT-vertex-staging/
  pipeline-root/          # VERTEX_AI_PIPELINE_ROOT — KFP snapshots
  staging/                # Vertex SDK staging
gs://CLIENT-vertex-models/
  favorita_store_n1d_xgboost/ # inputs.gcs_model_path per config
```

## Labels (chargeback)

Set for every deployment:

```bash
GCP_ENVIRONMENT=prod          # or dev / staging
GCP_CLIENT_LABEL=acme-corp    # client slug
```

Per-config overrides: `vertex.labels` in `model_config.yaml`.

## Cloud Scheduler

Schedule **dbt features first**, then **Vertex pipeline** (or train-only for cheap refreshes).

Example: HTTP target calling **Cloud Run** or **Cloud Functions** that runs:

```bash
python -m vertex.jobs.submit_pipeline --pipeline favorita_xgboost --sync
```

See [cloud_scheduler.example.json](cloud_scheduler.example.json) for a Scheduler + Cloud Run pattern outline.

Alternative: **Workflows** orchestrating dbt Cloud job → Vertex PipelineJob API.

## Monitoring

- Vertex AI → Pipelines / Training: job failures, duration
- BigQuery: `ml_vertex_job_runs` for status `FAILED`
- Cloud Logging: filter `resource.type="aiplatform.googleapis.com/PipelineJob"`

## CI vs production

| Action | CI | Production |
|--------|----|--------------|
| `pytest -m unit` | Yes | Optional smoke |
| `vertex.pipelines.compile` | Yes | Part of release artifact |
| `submit_pipeline` | No | Scheduler / manual approval |

## Security checklist

- [x] Production container runs as a non-root user and excludes compilers, Git, and curl;
      CI actions and the Python base image are pinned to immutable revisions
- [x] Vertex Custom Jobs authenticate via their attached service account + ADC (instance
      metadata server) — no key file is propagated into the job container
      (`vertex/jobs/gcp.py`). See `docs/specs/workload_identity_federation.md`.
- [x] CI Workload Identity Federation for jobs that need real GCP access. The reference dev
      environment was live-accepted on 2026-07-18 with repository-scoped GitHub OIDC, federated
      project access, and a keyless remote-state Terraform plan; repeat the documented bootstrap
      for each client (`docs/specs/workload_identity_federation.md`)
- [ ] Service account keys not stored in repo for **local dev** submission identity; key file
      remains the supported path there (see spec's non-goals) — Secret Manager as an alternative
- [ ] Artifact Registry image scanning enabled
- [ ] VPC-SC or private IP for Vertex (enterprise)
- [ ] CMEK on GCS buckets (if required)
- [ ] Separate GCP projects for dev / prod
