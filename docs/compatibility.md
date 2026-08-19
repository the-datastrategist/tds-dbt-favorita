# Compatibility policy

| Layer | Supported baseline | Notes |
|---|---|---|
| Python | 3.11 | CI authority; later compatible versions are best effort |
| Node.js | 22.12+ | ForecastLab engines contract |
| React / Vite | Pinned in `frontend/package.json` | Lockfile required |
| dbt Core / dbt-bigquery | Pinned in `requirements.txt` | BigQuery adapter is authoritative |
| Prefect | Pinned in `requirements.txt` | Deployment schema may evolve before 1.0 |
| Terraform | Provider lockfiles per environment | Validate dev and prod modules |
| FastAPI `/v1` | Additive changes preferred | Breaking changes require a new version or migration |
| Warehouse contracts | Append-only evidence and compatibility views | Never rewrite accepted evidence |
| GitHub Pages | Current Chromium plus modern evergreen browsers | Synthetic, read-only fixture mode |

Before 1.0, maintainers may change internal Python module paths and Terraform inputs with migration
notes. Persisted IDs, accepted warehouse evidence, and published `/v1` response meaning receive the
strongest compatibility protection.
