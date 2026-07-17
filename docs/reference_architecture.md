{% docs reference_architecture %}

# Reference architecture — GCP demand forecasting

Modern demand forecasting on Google Cloud typically separates **feature engineering in the warehouse**, **model training** (warehouse-native or custom), **orchestration**, and **consumption** (BI, planning systems, or APIs). This project implements that pattern on BigQuery + Vertex AI.

The architecture is intentionally GCP-specific. Portability across clouds is out of scope; portability across forecasting projects comes from contracts, dbt conventions, and configuration.

---

## Logical layers

| Layer | GCP services | This repo |
|-------|--------------|-----------|
| **Ingestion** | GCS, BigQuery load jobs | Source-specific loaders into a raw BigQuery dataset |
| **Analytics engineering** | BigQuery, dbt | Project-owned staging, feature, eligibility, and mart models |
| **ML — warehouse** | BigQuery ML | `dbt/models/marts/ml_models/bqml_model_*` |
| **ML — custom** | Vertex Custom Jobs, PipelineJobs, GCS | `vertex/` + `model_config.yaml` |
| **Orchestration** | Prefect OSS (local) → Cloud Scheduler / Workflows (prod) | `orchestration/`, `prefect.yaml` |
| **Experiment tracking** | MLflow, Vertex AI Experiments | `vertex/utils/experiment_tracking.py` |
| **Metadata & predictions** | BigQuery tables | `vertex/ddl/vertex_bq_tables.sql` |
| **Consumption** | Looker, Looker Studio, Sheets, APIs | dbt exposures + `stg_vertex_*` (BI layer blueprint) |

---

## End-to-end data flow

```mermaid
flowchart LR
  subgraph Ingest
    Source[Operational source data]
    GCS[(GCS raw bucket)]
    BQRaw[(BigQuery raw dataset)]
    Source --> GCS --> BQRaw
  end

  subgraph dbt["dbt on BigQuery"]
    Stg[staging]
    Int[int_sales_* features]
    BQML[bqml_model_*]
    StgVertex[stg_vertex_*]
    BQRaw --> Stg --> Int
    Int --> BQML
  end

  subgraph Vertex["Vertex AI custom ML"]
    Train[train]
    Opt[optimize]
    Pred[predict]
    GCSModels[(GCS model artifacts)]
    BQMeta[(forecast / model metadata tables)]
    Int --> Train
    Int --> Opt --> Train --> Pred
    Train --> GCSModels
    Train --> BQMeta
    Pred --> BQMeta
  end

  subgraph Track["Experiment tracking"]
    MLflow[MLflow]
    VExp[Vertex Experiments]
    Train -.-> MLflow
    Train -.-> VExp
  end

  BQMeta --> StgVertex
  subgraph Consume["Consumption (planned / client-specific)"]
    BI[Dashboard / planning]
    StgVertex --> BI
    BQML --> BI
  end
```

---

## Daily / weekly operational flow

```mermaid
sequenceDiagram
  participant Sched as Scheduler / Prefect
  participant dbt as dbt run
  participant BQ as BigQuery
  participant V as Vertex pipeline
  participant GCS as GCS artifacts
  participant ML as MLflow

  Sched->>dbt: Refresh staging + int_sales_*
  dbt->>BQ: Materialize feature tables
  Sched->>V: PipelineJob (optimize → train → predict)
  V->>BQ: Read train_sql_query / predict_sql_query
  V->>GCS: Write model.joblib + manifest.json
  V->>BQ: MERGE metadata, performance, predictions
  V->>ML: Log params, metrics, gcs_model_catalog.json
  Sched->>dbt: dbt-vertex (stg_vertex_* views)
```

Recommended schedule (implemented in `prefect.yaml`):

1. **06:00 UTC** — dbt feature refresh (`prefect-dbt-run-scheduled`)
2. **07:00 UTC** — optional train-only Custom Job
3. **Sunday 08:00 UTC** — full XGBoost pipeline (`prefect-vertex-ml-pipeline-scheduled`)

Production clients typically replace Prefect OSS with **Cloud Scheduler → Cloud Run/Workflows** calling the same Python entrypoints (`vertex/ops/README.md`).

---

## Dual ML path (same features, different tradeoffs)

```mermaid
flowchart TB
  Features[int_sales_* in BigQuery]

  Features --> BQMLPath[BigQuery ML path]
  Features --> VertexPath[Vertex custom path]

  subgraph BQMLPath
    BT[BOOSTED_TREE_REGRESSOR]
    BQPred[Batch predict in SQL]
    BQEval[EVALUATE + EXPLAIN]
  end

  subgraph VertexPath
    Registry[model_type registry]
    XGB[xgboost / random_forest]
    TS[arima / sarima]
    GCSArt[GCS artifacts]
    Unified[canonical forecast output]
  end

  BQMLPath --> BQPred
  VertexPath --> Unified
```

| Dimension | BigQuery ML | Vertex custom (this repo) |
|-----------|-------------|---------------------------|
| **Best for** | Fast baseline, SQL-only teams, low ops | Custom algorithms, Optuna tuning, multi-step pipelines |
| **Training** | `CREATE MODEL` via dbt macros | Custom Jobs / KFP PipelineJobs |
| **Artifacts** | BQ model registry | GCS joblib + manifest (MLflow catalog pointer) |
| **Predictions** | `ML.PREDICT` in dbt | Python runners → unified BQ fact table |
| **Feature input** | `int_sales_daily` (default) | `int_sales_store_daily` (default XGBoost config) |
| **Experiment tracking** | BQML evaluate tables | MLflow + Vertex Experiments + BQ performance |

---

## Project-specific dbt feature layer

Forecasting granularity is a core architecture decision. The platform expects each implementation to provide dbt models that express its planning grains, entity keys, target definition, and covariates.

| Layer | Project responsibility |
|-------|------------------------|
| Raw sources | Land source data in BigQuery with reproducible ingestion |
| Staging | Clean, type, deduplicate, and document source-aligned tables |
| Features | Build point-in-time-correct training/scoring features at selected grains |
| Eligibility | Define which entities/dates should be forecasted and why exclusions occur |
| Marts | Expose forecast-ready inputs and downstream forecast outputs |

This is the canonical adapter layer: a new project adapts raw demand, product, location, calendar, price, promotion, inventory, and other operational sources into the feature and contract shape used by the platform. A formal plugin/connector framework is out of scope for now.

---

## Security & environments (production pattern)

```mermaid
flowchart TB
  subgraph Dev
    DevProj[GCP project dev]
    DevSA[sa-vertex-ml-dev]
  end
  subgraph Prod
    ProdProj[GCP project prod]
    ProdSA[sa-vertex-ml-prod]
  end

  DevProj --> DevSA
  ProdProj --> ProdSA

  ProdSA --> BQEditor[BigQuery dataEditor scoped datasets]
  ProdSA --> GCSBucket[GCS objectAdmin scoped buckets]
  ProdSA --> VertexUser[aiplatform.user]
```

See [iac.md](iac.md) and `vertex/ops/README.md` for IAM roles, chargeback labels (`GCP_CLIENT_LABEL`, `GCP_ENVIRONMENT`), and the security checklist.

---

## CI/CD architecture

```mermaid
flowchart LR
  PR[Pull request] --> GHA[GitHub Actions]
  GHA --> Lint[black / flake8 / mypy]
  GHA --> Test[pytest unit ≥65% cov]
  GHA --> Config[validate model_config.yaml]
  GHA --> KFP[compile KFP pipeline JSON]
  GHA --> dbt[dbt parse / compile / docs]
  main[Push to main] --> Pages[GitHub Pages dbt Docs]
```

Warehouse-backed runs (`dbt run`, `dbt test`, Vertex submit) execute in the client GCP project after credentials are configured — not in CI.

---

## Related documents

- [Accelerators](accelerators.md) — what is implemented in this repo
- [Case study](case_study.md) — business framing
- Product views: [dbt](dbt/consulting_package.md) · [Vertex](vertex/consulting_package.md) · [MLflow](mlflow/consulting_package.md) · [Prefect](prefect/consulting_package.md)

{% enddocs %}
