{% docs iac %}

# Infrastructure as code and GCP operations

Guidance for provisioning and operating this forecasting stack in a **client GCP organization**. Operational runbooks and **Terraform modules** are both **available today**.

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
| **Terraform modules** | `terraform/` | Versioned, reviewable GCP provisioning (see below) |

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

### Local / orchestrator identity (defense-in-depth)

`sa-vertex-ml` above is the identity **Vertex Custom Jobs and PipelineJobs run as**. It's a
separate concern from the identity the `ml-pipeline` container itself uses locally
(`GOOGLE_APPLICATION_CREDENTIALS`, e.g. a key for `sa-vertex-local-dev@PROJECT`) — the container
needs to run `dbt` and raw ingestion (which always write directly to BigQuery/GCS, no Vertex
equivalent) plus optionally exercise `VERTEX_MODE=docker` for fast local ML iteration. Only
`sa-vertex-ml` should ever run scheduled/production ML training, predict, and optimize — see
[overview.md](overview.md#system-diagram) and `prefect.yaml` (`vertex_mode: vertex` on every
`*-schedule` deployment).

To keep that boundary enforced by IAM rather than convention alone in staging/prod:

| Role | Scope | Grant to |
|------|-------|----------|
| `roles/bigquery.dataEditor` | Dataset `raw_favorita`, staging/feature portion of `favorita` | Local/orchestrator identity (dbt writes) |
| `roles/bigquery.jobUser` | Project | Both identities (dbt and Vertex both run queries) |
| `roles/storage.objectAdmin` | Raw bucket only | Local/orchestrator identity (ingestion) |
| `roles/aiplatform.user` | Project | Local/orchestrator identity (submit only — no compute) |
| `roles/bigquery.dataEditor` | ML output tables (`ml_model_*`, `ml_vertex_job_runs`, `backtest_*`, `forecast_*`) | `sa-vertex-ml` only |
| `roles/storage.objectAdmin` | Staging + models buckets | `sa-vertex-ml` only |

Caveat: the ML output tables above live in the **same** `favorita` dataset as the dbt feature
models (see `vertex/ddl/vertex_bq_tables.sql`), and BigQuery dataset-level IAM can't separate
them from dbt-owned tables. Enforcing the split with a dataset-level grant alone isn't possible;
either use BigQuery **table-level** IAM bindings on just the `ml_*`/`backtest_*`/`forecast_*`
tables, or move them to a dedicated dataset (e.g. `favorita_ml`) that only `sa-vertex-ml` can
write to. Until one of those is in place, treat `VERTEX_MODE=vertex`-only scheduling as the
primary control and this IAM split as defense-in-depth, not a hard guarantee.

---

## GCS layout (recommended)

```text
gs://CLIENT-raw/
  favorita/                    # or client source prefix (GCS_RAW_DATA_BUCKET)

gs://CLIENT-vertex-staging/
  staging/                     # VERTEX_AI_STAGING_BUCKET
  pipeline-root/               # VERTEX_AI_PIPELINE_ROOT — KFP snapshots

gs://CLIENT-vertex-models/
  favorita_store_n1d_xgboost/            # inputs.gcs_model_path per config
  favorita_store_n1d_rf/
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

Tables: `ml_vertex_job_runs`, `ml_model_metadata`, `ml_model_performance`, `ml_model_optimize`, `ml_model_predictions`.

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
| Job audit | `SELECT * FROM ml_vertex_job_runs WHERE status = 'FAILED'` |
| Logs | Cloud Logging: `resource.type="aiplatform.googleapis.com/PipelineJob"` |
| Model quality | [benchmarks.md](benchmarks.md) queries on performance tables |

---

## Security checklist

From `vertex/ops/README.md`:

- [x] Production container runs as a non-root user and excludes compilers, Git, and curl;
      CI actions and the Python base image are pinned to immutable revisions
- [x] Vertex Custom Jobs authenticate via their attached service account + ADC (no key file
      propagated into the job container — fixed in `vertex/jobs/gcp.py`)
- [x] CI **Workload Identity Federation** for jobs that need real GCP access: the reference dev
      pool/provider, repository-scoped principal, CI service account, protected GitHub variables,
      federated identity check, and keyless Terraform plan were live-accepted on 2026-07-18
      ([spec](specs/workload_identity_federation.md)); repeat `make bootstrap-gcp` per client
- [ ] Service account keys not in repo for **local dev**; key file remains the supported path
      there per the WIF spec's non-goals
- [ ] Artifact Registry **vulnerability scanning** enabled
- [ ] VPC-SC or private IP for Vertex (enterprise)
- [ ] **CMEK** on GCS buckets if required
- [ ] Separate GCP projects for **dev / prod**
- [x] Offline CI parse/compile jobs use placeholder credentials only; authenticated dev planning
      uses WIF and never stores a service-account JSON secret

---

## Terraform

`terraform/` now codifies the sections above as versioned modules. Full design: [specs/terraform_modules.md](specs/terraform_modules.md); usage: [`terraform/README.md`](../terraform/README.md).

```text
terraform/
  modules/
    gcp-apis/           # Enable required APIs
    bigquery-datasets/  # raw + analytics datasets
    gcs-buckets/        # raw, staging, models, mlflow
    artifact-registry/  # Docker repository
    iam-vertex-sa/      # SA + custom bucket/dataset bindings
    cloud-scheduler/    # Optional HTTP jobs, disabled by default
  environments/
    dev/
    prod/
```

CI runs `fmt`/`validate` on every PR touching `terraform/` (`.github/workflows/terraform.yml`);
`plan`/`apply` stay manual/local until CI has a way to authenticate to GCP at all (see
[Workload Identity Federation](specs/workload_identity_federation.md)).

**New environments:** `terraform apply` from `terraform/environments/{dev,prod}`, then
`make vertex-bq-ddl` for table schemas (kept out of Terraform — see the spec's Non-goals) and
push the Docker image to Artifact Registry.

**Existing environments (already provisioned via the shell scripts):** `terraform import` each
resource before ever running `apply` — see the spec's Migration plan. The shell scripts
(`scripts/setup_vertex_*.sh`) remain the quickest path for a brand-new environment or as the
source of truth to import from; they are not being retired.

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
- [Engineering specs](specs/README.md) — Terraform modules, Workload Identity Federation

{% enddocs %}
