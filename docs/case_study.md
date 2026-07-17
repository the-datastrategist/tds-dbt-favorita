{% docs case_study %}

# Case study — GCP demand forecasting platform

**Client context (synthetic):** A multi-location business needs daily operational demand forecasts that account for known-future business events, calendar effects, pricing, promotions, and other project-specific covariates. Data lives in BigQuery; the analytics team uses dbt; ML engineers want both quick baselines and tunable custom models.

**Engagement type:** Production-style GCP platform implementation — built to demonstrate The Data Strategist's demand forecasting delivery pattern.

---

## Business problem

Retailers must answer:

> *How much will each store sell tomorrow — and over the next week — by category and SKU, given promotions and calendar effects?*

Poor forecasts drive **overstock, stockouts, and wasted labor** in replenishment, staffing, and capacity planning. The platform is designed for projects where demand varies across entities, time, hierarchy, and known-future business drivers.

### Success criteria

| Criterion | Target |
|-----------|--------|
| **Reproducible features** | Single governed feature layer in BigQuery, documented in dbt |
| **Multiple model paths** | Warehouse-native baseline + custom Python for advanced algorithms |
| **Auditable outputs** | Predictions, metadata, and job runs queryable in SQL |
| **Operational refresh** | Scheduled pipeline: features → train → predict |
| **Handoff-ready** | Docker, config YAML, CI, ops runbook |

---

## Constraints

| Constraint | Implication |
|------------|-------------|
| GCP-first stack | BigQuery + Vertex AI + GCS (no alternate warehouse) |
| Small platform team | Prefer config over custom code per model |
| Cost sensitivity | BQML for baseline; Vertex for tuning and time-series |
| Governance | dbt tests, exposures, lineage for ML consumers |
| Reusable GCP boundary | No alternate warehouse or cloud target in scope |

---

## Approach

### 1. Analytics engineering first

Raw operational data lands in BigQuery. dbt builds:

- **Staging** — typed, incremental source-aligned tables
- **Intermediate** — feature tables at the project's chosen aggregate, location, product, or other planning grains
- **Tests** — grain uniqueness, `not_null`, row-count assertions

*Why:* ML quality ceiling is set by features. Governed SQL features are reusable by BQML, Vertex, and BI. This dbt layer is intentionally project-specific.

### 2. Dual ML paths on shared features

```mermaid
flowchart LR
  Features[int_sales_*]
  Features --> BQML[BigQuery ML BOOSTED_TREE]
  Features --> Vertex[XGBoost / RF / ARIMA / SARIMA]
  BQML --> Out1[SQL predictions + EXPLAIN]
  Vertex --> Out2[Unified BQ prediction table + GCS artifacts]
```

- **BQML** — fastest path to a boosted-tree baseline with `EVALUATE` and global feature attribution in SQL
- **Vertex** — Optuna hyperparameter search, multi-algorithm registry, KFP pipelines, GCS model artifacts, and per-prediction SHAP explainability for tree models

*Why:* Clients rarely commit to one ML platform on day one. This architecture supports a phased roadmap.

### 3. Config-driven custom ML

All Vertex jobs are declared in `vertex/config/model_config.yaml` — train SQL, target column, model params, GCS paths, and output tables. New models register in `vertex/models/registry.py` without new CLI scripts.

### 4. Orchestration and observability

Prefect OSS schedules dbt and ML pipelines locally; production maps to Cloud Scheduler + Cloud Run. Every Vertex job logs to **BigQuery** (metadata, performance), **MLflow** (metrics + GCS catalog), and **Vertex Experiments**.

### 5. Production path documented

`vertex/ops/README.md` covers least-privilege IAM, GCS layout, chargeback labels, and monitoring queries — ready to adapt per client org.

---

## Outcomes (reference implementation)

Outcomes below reflect **architectural deliverables**. Numeric benchmarks are populated per environment — see [benchmarks.md](benchmarks.md).

| Outcome | Evidence in repo |
|---------|------------------|
| End-to-end feature pipeline | `make dbt-run` → four `int_sales_*` tables |
| BQML baseline | `make dbt-train`, `bqml_model_evaluate` |
| Four Vertex model families | XGBoost, RF, ARIMA, SARIMA configs in YAML |
| Hyperparameter search | Optuna optimize step + model optimize table |
| Per-prediction explainability | SHAP top-feature attributions for tree models |
| Unified predictions | BigQuery prediction / forecast output tables |
| Experiment tracking | MLflow UI (`make mlflow-ui`), Vertex Experiments |
| CI without GCP | GitHub Actions: lint, test, config validate, KFP compile |
| Lineage for ML consumers | `dbt/models/exposures.yml` |

---

## What we would change for a real client

| Area | Reference repo | Typical client adaptation |
|------|----------------|---------------------------|
| Data source | Demo or initial project source files in GCS | ERP / POS / promo feeds, incremental loads |
| Grain | Store-day default for Vertex | SKU-level or DC-level per use case |
| Orchestration | Prefect OSS in Docker | Cloud Composer, Workflows, or client scheduler |
| Auth | Service account JSON (dev) | Workload Identity Federation, Secret Manager |
| Dashboard | Blueprint only | Looker, Looker Studio, or embedded app |
| Model champion | Manual comparison | Automated leaderboard mart + alerts |
| Cost | Dev-sized queries | Partition pruning, BQ reservations, spot/preemptible Vertex |

---

## Technology choices (summary)

| Choice | Rationale |
|--------|-----------|
| **dbt on BigQuery** | Industry-standard analytics engineering; docs + lineage |
| **BigQuery ML** | Low-lift baseline inside the warehouse |
| **Vertex Custom Jobs** | Full Python control, Artifact Registry image |
| **KFP Pipelines** | optimize → train → predict as one auditable unit |
| **MLflow** | Portable experiment tracking; GCS remains artifact source of truth |
| **Prefect OSS** | Lightweight orchestration without managed Composer cost for demos |
| **Docker + Makefile** | Repeatable local and CI environment |

---

## Related documents

- [Reference architecture](reference_architecture.md) — diagrams and flows
- [Benchmarks](benchmarks.md) — metric comparison template
- [Client rollout](client_rollout.md) — engagement timeline
- [Consulting package](consulting_package.md) — full package overview

{% enddocs %}
