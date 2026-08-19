{% docs spec_open_source_product_readiness %}

# SPEC: Open-source product readiness

**Status:** In progress
**Roadmap reference:** [Specs overview](README.md) — P3 "Open-source product readiness"

---

## Summary

The repo is strong as a GCP demand forecasting foundation, but open-source users need a self-contained first run, contribution and release governance, clear platform boundaries, compatibility promises, and clear scope language.

This spec adds `docs/open_source_governance.md`, `docs/product_roadmap.md`, community files, a local quickstart, and a modularization plan that separates reusable platform contracts from project-specific dbt implementations.

Implementation checkpoint (2026-08-19): governance/community files, product roadmap, compatibility
policy, extension guide, and the deterministic `make quickstart-local` workflow are implemented and
CI-enforced. The gradual platform-core modularization and second project implementation remain.

## Goals

- Add community and release governance files.
- Make the first-run experience self-contained without mandatory GCP credentials.
- Provide a completed reference benchmark and expected outputs.
- Clarify implemented, planned, experimental, and deployment-specific scope.
- Document compatibility across Python, dbt, BigQuery, Vertex, Prefect, Terraform, and optional dependencies.
- Define extension guides for model families, dbt project implementations, and forecast destinations.
- Create a migration path toward platform core plus project examples.

## Non-goals

- Completing the full modular refactor in one change.
- Supporting non-GCP production deployment.
- Building a plugin marketplace, remote connector service, or independent extension package
  distribution system. Typed in-process extension interfaces are specified separately in
  [platform generalization](platform_generalization.md).
- Guaranteeing long-term API stability before the first public release policy is written.

## Design

### 1. Governance and community files

Add:

- `CONTRIBUTING.md`
- `CODE_OF_CONDUCT.md`
- `SECURITY.md`
- `SUPPORT.md`
- `CHANGELOG.md`
- `.github/ISSUE_TEMPLATE/`
- `.github/PULL_REQUEST_TEMPLATE.md`
- `docs/open_source_governance.md`
- `docs/product_roadmap.md`

`LICENSE` already exists and should remain MIT unless project policy changes.

### 2. Self-contained quickstart

Add `docs/quickstart_local.md` and a command that runs without user-managed GCP:

```bash
make quickstart-local
```

Acceptable implementation options:

- synthetic demand dataset
- small checked-in seed dataset
- automated public-data download with caching
- local DuckDB/SQLite demo path if BigQuery is unavailable

Quickstart output should include:

- generated features
- at least one baseline forecast
- one benchmark table
- one forecast output artifact
- cleanup command

### 3. Completed reference benchmark

Replace or supplement placeholder benchmark tables with a known reproducible result from the local or synthetic quickstart path. Include expected row counts and example output snippets.

### 4. Product roadmap

Add `docs/product_roadmap.md` with sections:

- implemented
- in progress
- experimental
- planned
- out of scope
- deployment-specific examples, if any

Use the recommendation document's scope clarification:

- current repo: production-style GCP demand forecasting platform foundation
- after P0/P1: demand forecasting engine with stronger reusable contracts
- after P2: end-to-end demand forecasting platform

### 5. Modularization plan

Document target layout:

```text
forecasting_core/
examples/
deploy/gcp/
ui/
docs/
```

Implementation should proceed gradually:

1. Move generic contract/evaluation utilities first.
2. Keep the current dbt models and configs working while re-labeling them as a project implementation.
3. Add compatibility shims for old import paths.
4. Move GCP-specific Terraform under `deploy/gcp/` only when docs and CI are updated.

## Implementation plan

1. Add governance/community files.
2. Add `docs/open_source_governance.md` and `docs/product_roadmap.md`.
3. Add local quickstart design and minimal implementation.
4. Add compatibility matrix.
5. Add extension guides for model families, dbt project implementations, and forecast destinations.
6. Start modularization with generic contracts/evaluation code.

## Testing & validation

- CI verifies quickstart smoke test.
- Link check or docs generation includes new docs.
- Secret scan before public release.
- Fresh-clone test following only quickstart docs.
- PR template requires test evidence and docs update notes.

## Acceptance criteria

- A new contributor can run a forecast example without manually provisioning GCP.
- Public contribution/security/support policies exist.
- Roadmap language does not overclaim end-to-end platform status before P0/P2 work lands.
- The repo has an explicit extension path for model families, dbt project implementations, and forecast destinations.

## Related documents

- [Forecast contract and canonical output](forecast_contract_and_output.md)
- [Backtesting and model lifecycle](backtesting_and_model_lifecycle.md)
- [Integration contracts](integration_contracts.md)
- [Platform generalization](platform_generalization.md)

{% enddocs %}
