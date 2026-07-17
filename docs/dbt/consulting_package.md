{% docs dbt_consulting_package %}

# dbt consulting package — GCP demand forecasting platform

**dbt's role** in this engagement: govern the **analytics engineering layer** — raw → staging → ML features → BQML marts → Vertex output staging — with tests, lineage, and documented exposures for ML and BI consumers.

The dbt layer is intentionally project-specific. Builders should adapt or replace staging and feature models so their own operational sources map into forecast-ready targets, grains, covariates, eligibility rules, and marts.

Parent overview: [consulting_package.md](../consulting_package.md)

---

## dbt in the three-layer package

```mermaid
flowchart TB
  subgraph L1["Reference architecture"]
    Layers[Medallion: raw → staging → intermediate → marts]
    Dual[Same int_sales_* feeds BQML + Vertex]
  end

  subgraph L2["dbt accelerators"]
    Stg[staging incremental models]
    Int[int_sales_* partitioned tables]
    BQML[bqml_model_* macros]
    VStg[stg_vertex_* views]
    Exp[exposures.yml]
    Sel[selectors.yml]
  end

  subgraph L3["Delivery artifacts"]
    Docs[dbt Docs + GitHub Pages]
    CS[Case study — features-first narrative]
    BM[Benchmarks — BQML evaluate queries]
    DB[Dashboard blueprint — stg_vertex_* + int_sales_*]
  end

  L1 --> L2 --> L3
```

---

## Reference architecture (dbt lens)

| Layer | Models | Materialization | Tags |
|-------|--------|-----------------|------|
| **Sources** | project raw dataset | External | — |
| **Staging** | source-specific staging, `stg_vertex_*` | Incremental / view | `staging`, `vertex` |
| **Intermediate** | `int_sales_*` | Partitioned table | `train`, `features` |
| **Marts** | `bqml_model_*` | View (BQML ops) | `bqml` |

### Data flow

```mermaid
flowchart LR
  Raw[(raw dataset)] --> Stg[staging]
  Stg --> Int[int_sales_*]
  Int --> BQML[bqml_model_train / predict / evaluate]
  Int -.->|SQL in model_config| Vertex[Vertex jobs]
  Vertex --> BQSrc[(model / forecast tables)]
  BQSrc --> VStg[stg_vertex_*]
  VStg --> BI[Dashboard blueprint]
  Int --> Exp[exposures: ML consumers]
```

---

## Accelerators (dbt-specific)

| Asset | Path |
|-------|------|
| Project config | `dbt/dbt_project.yml` |
| Staging | `dbt/models/staging/` |
| Features | `dbt/models/intermediate/int_sales_*.sql` |
| BQML | `dbt/models/marts/ml_models/`, `dbt/macros/` |
| Vertex sources | `dbt/models/sources/vertex.yml` |
| Vertex staging | `dbt/models/staging/stg_vertex_*.sql` |
| Tests | `dbt/models/*/schema.yml`, `dbt/tests/` |
| Selectors | `dbt/selectors.yml` |
| Exposures | `dbt/models/exposures.yml` |
| Overview | `docs/overview.md` |

### Key commands

```bash
make dbt-run              # staging + intermediate (excludes bqml)
make dbt-train            # BQML CREATE MODEL
make dbt-predict          # BQML batch predict
make dbt-vertex           # stg_vertex_* over ML outputs
make dbt-test             # data quality
make dbt-docs-generate    # catalog + lineage
```

### Feature grains (consulting talking points)

| Model | Grain | Default for |
|-------|-------|-------------|
| `int_sales_daily` | company-day | BQML, executive forecast |
| `int_sales_store_daily` | store-day | Vertex XGBoost / RF / ARIMA |
| `int_sales_store_product_daily` | store-SKU-day | Item demand |
| `int_sales_store_product_family_daily` | store-family-day | Category planning |

---

## Delivery artifacts (dbt-specific)

| Artifact | How dbt supports it |
|----------|---------------------|
| **Case study** | "Analytics engineering first" — features before ML |
| **Benchmarks** | Query `bqml_model_evaluate`; join Vertex via sources |
| **Dashboard** | Expose `stg_vertex_model_predictions` + `int_sales_store_daily` |
| **Rollout** | Week 2 = dbt staging + tests; Week 4 = `dbt-vertex` |
| **Lineage** | Exposures for forecast, training, prediction, calendar, and master-data consumers |

### Exposures for client conversations

Open dbt Docs lineage and highlight the project exposures for:

- BQML end-to-end forecasts
- feature tables feeding Vertex
- unified ML outputs feeding BI / planning consumers
- operational calendar and known-future covariates

---

## Client customization (dbt)

1. Add client sources in `dbt/models/raw/` or update `sources.yml`
2. Adapt staging column names / grains
3. Add or trim `int_sales_*` feature columns
4. Register new BQML config in `dbt_project.yml` → `vars.model_configs`
5. Add dashboard exposure when BI layer exists

---

## Related documents

- [Full reference architecture](../reference_architecture.md)
- [Accelerators](../accelerators.md)
- [Client rollout](../client_rollout.md) — Week 2 dbt focus
- Other products: [Vertex](../vertex/consulting_package.md) · [MLflow](../mlflow/consulting_package.md) · [Prefect](../prefect/consulting_package.md)

{% enddocs %}
