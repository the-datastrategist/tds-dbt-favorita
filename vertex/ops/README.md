# Vertex operations (GCP)

Runbook for productionizing this template in a client GCP organization.

## IAM (least privilege)

Create a **Vertex AI service account** per environment (e.g. `sa-vertex-ml@PROJECT.iam.gserviceaccount.com`) with:

| Role | Purpose |
|------|---------|
| `roles/aiplatform.user` | Submit Custom Jobs and PipelineJobs |
| `roles/storage.objectAdmin` | Staging bucket, model artifacts, pipeline root (scope to bucket IAM) |
| `roles/bigquery.dataEditor` | Write metadata, predictions, job runs |
| `roles/bigquery.jobUser` | Run queries for training data |

Prefer **bucket-level** IAM for GCS instead of project-wide `objectAdmin` when possible.

Set in `.env`:

```bash
VERTEX_PIPELINE_SERVICE_ACCOUNT=sa-vertex-ml@PROJECT.iam.gserviceaccount.com
```

Custom Jobs and PipelineJobs use this account when set.

## GCS layout (recommended)

```text
gs://CLIENT-vertex-staging/
  pipeline-root/          # VERTEX_AI_PIPELINE_ROOT — KFP snapshots
  staging/                # Vertex SDK staging
gs://CLIENT-vertex-models/
  favorita_xgboost_train/ # inputs.gcs_model_path per config
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
- BigQuery: `favorita_vertex_job_runs` for status `FAILED`
- Cloud Logging: filter `resource.type="aiplatform.googleapis.com/PipelineJob"`

## CI vs production

| Action | CI | Production |
|--------|----|--------------|
| `pytest -m unit` | Yes | Optional smoke |
| `vertex.pipelines.compile` | Yes | Part of release artifact |
| `submit_pipeline` | No | Scheduler / manual approval |

## Security checklist

- [ ] Service account keys not stored in repo; use WIF or Secret Manager
- [ ] Artifact Registry image scanning enabled
- [ ] VPC-SC or private IP for Vertex (enterprise)
- [ ] CMEK on GCS buckets (if required)
- [ ] Separate GCP projects for dev / prod
