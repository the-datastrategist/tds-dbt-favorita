{% docs iac %}

# Infrastructure as code and GCP operations

Guidance for provisioning and operating this forecasting stack in a **client GCP organization**. Operational runbooks are **available today**; full **Terraform modules are roadmapped**.

---

## What is available now

| Asset | Location | Contents |
|-------|----------|----------|
| **Ops runbook** | `vertex/ops/README.md` | IAM, GCS layout, labels, Scheduler, monitoring, security checklist |
| **Env contract** | `env.example` | All required variables for Docker / Vertex / dbt |
| **DDL scripts** | `vertex/ddl/vertex_bq_tables.sql` | BigQuery tables for ML outputs |
| **DDL applicator** | `scripts/apply_vertex_bq_ddl.py` | `make vertex-bq-ddl` |
| **Docker image** | `Dockerfile`, `docker-compose.yml` | Reproducible runtime |
| **CI pipeline** | `.github/workflows/ci.yml` | Validate without live GCP |

---

## Target GCP architecture

```mermaid
flowchart TB
  subgraph Project["GCP project (per env)"]
    APIs[Enabled APIs: BQ, GCS, Vertex, Artifact Registry]
    AR[Artifact Registry: tds-favorita image]
    BQ[(BigQuery datasets)]
    GCSRaw[(GCS raw)]
    GCSStage[(GCS vertex-staging)]
    GCSModels[(GCS models)]
    SA[sa-vertex-ml@PROJECT.iam.gserviceaccount.com]
  end

  subgraph External
    GHA[GitHub Actions CI]
    Sched[Cloud Scheduler]
    CR[Cloud Run trigger optional]
  end

  SA --> BQ
  SA --> GCSStage
  SA --> GCSModels
  AR --> VertexJobs[Vertex Custom Jobs / Pipelines]
  VertexJobs --> SA
  Sched --> CR
  CR --> VertexJobs
  GHA -.->|build push| AR
```

---

## IAM matrix (least privilege)

Create **`sa-vertex-ml@PROJECT.iam.gserviceaccount.com`** per environment.

| Role | Scope | Purpose |
|------|-------|---------|
| `roles/aiplatform.user` | Project | Submit Custom Jobs and PipelineJobs |
| `roles/bigquery.jobUser` | Project | Run training/scoring queries |
| `roles/bigquery.dataEditor` | Dataset `favorita`, `raw_favorita` | Write ML output tables |
| `roles/storage.objectAdmin` | Bucket-level on staging + models | Artifacts and pipeline root |

Prefer **bucket-level** GCS IAM over project-wide storage admin.

Set in `.env`:

```bash
VERTEX_PIPELINE_SERVICE_ACCOUNT=sa-vertex-ml@PROJECT.iam.gserviceaccount.com
```

Custom Jobs and PipelineJobs use this account when set.

---

## GCS layout (recommended)

```text
gs://CLIENT-raw/
  favorita/                    # or client source prefix (GCS_RAW_DATA_BUCKET)

gs://CLIENT-vertex-staging/
  staging/                     # VERTEX_AI_STAGING_BUCKET
  pipeline-root/               # VERTEX_AI_PIPELINE_ROOT — KFP snapshots

gs://CLIENT-vertex-models/
  favorita_xgboost/            # inputs.gcs_model_path per config
  favorita_rf/
  ...

gs://CLIENT-mlflow/            # optional MLFLOW_TRACKING_URI backend
```

---

## BigQuery datasets

| Dataset | Purpose |
|---------|---------|
| `raw_favorita` (or client raw) | Source-aligned tables |
| `favorita` (or `DBT_DATASET`) | dbt models + Vertex output tables |

Apply Vertex tables once per environment:

```bash
make vertex-bq-ddl
```

Tables: `favorita_vertex_job_runs`, `favorita_model_metadata`, `favorita_model_performance`, `favorita_model_optimize`, `favorita_model_predictions`.

---

## Chargeback labels

Set on every deployment for cost allocation:

```bash
GCP_ENVIRONMENT=prod          # dev | staging | prod
GCP_CLIENT_LABEL=acme-corp    # client slug
```

Per-config overrides: `vertex.labels` in `model_config.yaml`.

---

## Scheduling (production)

Schedule **dbt features first**, then **Vertex pipeline**.

**Pattern A — Cloud Scheduler → Cloud Run**

HTTP target invokes a Cloud Run service that runs:

```bash
python -m vertex.jobs.submit_pipeline --pipeline favorita_xgboost --sync
```

See `vertex/ops/README.md` for Scheduler outline (reference: `cloud_scheduler.example.json` when added).

**Pattern B — Prefect Cloud / self-hosted** — use `prefect.yaml` deployments (demo / mid-size).

**Pattern C — Workflows** — chain dbt Cloud job → Vertex PipelineJob API for enterprise.

Recommended cron (matches `prefect.yaml` defaults):

| Job | Cron (UTC) | Entrypoint |
|-----|------------|------------|
| dbt features | `0 6 * * *` | `dbt run --select tag:daily_refresh` |
| Vertex train | `0 7 * * *` | `vertex.jobs.run` or submit |
| Full ML pipeline | `0 8 * * 0` | `vertex.jobs.submit_pipeline` |

---

## Monitoring

| Signal | Where |
|--------|-------|
| Pipeline failures | Vertex AI → Pipelines / Training console |
| Job audit | `SELECT * FROM favorita_vertex_job_runs WHERE status = 'FAILED'` |
| Logs | Cloud Logging: `resource.type="aiplatform.googleapis.com/PipelineJob"` |
| Model quality | [benchmarks.md](benchmarks.md) queries on performance tables |

---

## Security checklist

From `vertex/ops/README.md`:

- [ ] Service account keys not in repo; prefer **Workload Identity Federation**
- [ ] Artifact Registry **vulnerability scanning** enabled
- [ ] VPC-SC or private IP for Vertex (enterprise)
- [ ] **CMEK** on GCS buckets if required
- [ ] Separate GCP projects for **dev / prod**
- [ ] CI uses placeholder credentials only (see `.github/workflows/ci.yml`)

---

## Terraform roadmap

Planned modules (not yet in repo) — structure for client engagements:

```text
terraform/
  modules/
    gcp-apis/           # Enable required APIs
    bigquery-datasets/  # raw + analytics datasets
    gcs-buckets/        # raw, staging, models, mlflow
    artifact-registry/  # Docker repository
    iam-vertex-sa/      # SA + custom bucket/dataset bindings
    cloud-scheduler/    # Optional HTTP jobs
  environments/
    dev/
    prod/
```

**Manual steps today:** create resources per sections above, then `make vertex-bq-ddl` and push Docker image to Artifact Registry.

**Variables to parameterize in Terraform:**

| Variable | Maps to |
|----------|---------|
| `project_id` | `GOOGLE_PROJECT_ID` |
| `region` | `VERTEX_AI_REGION` |
| `client_label` | `GCP_CLIENT_LABEL` |
| `environment` | `GCP_ENVIRONMENT` |
| `dbt_dataset` | `DBT_DATASET` |
| `raw_dataset` | `BQ_RAW_DATASET` |

---

## CI vs production

| Action | CI (GitHub Actions) | Production |
|--------|---------------------|------------|
| `pytest -m unit` | Yes | Optional smoke post-deploy |
| `vertex.pipelines.compile` | Yes | Part of release artifact |
| `submit_pipeline` / `submit` | No | Scheduler / manual approval |
| `dbt run` / `dbt test` | parse/compile only | Client warehouse |

---

## Related documents

- `vertex/ops/README.md` — operational detail
- [Client rollout](client_rollout.md) — when to provision each resource
- [Reference architecture](reference_architecture.md)

{% enddocs %}
