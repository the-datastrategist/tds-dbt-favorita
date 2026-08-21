# ADR 0002: Generalization begins at a validated deployment boundary

- **Status:** Accepted
- **Date:** 2026-08-20
- **Owners:** Forecasting platform maintainers

## Context

The Favorita implementation proves the forecasting contracts, but project, dataset, bucket,
frequency, and retail-entity assumptions remain distributed across configuration and operational
entry points. Removing all assumptions in one migration would change resource identity, temporal
semantics, model interfaces, and warehouse contracts simultaneously.

## Decision

Generalize the platform in contract-preserving phases. The first boundary is a typed deployment
manifest that validates cloud and warehouse identifiers before they are used. Core code resolves
fully qualified tables and GCS paths through a `ResourceCatalog`; project adapters continue to own
source-specific dbt models and entity mappings.

- Terraform environment inputs must name both raw and platform datasets explicitly.
- Reusable Terraform modules must not default to Favorita resource names.
- `make validate-deployment` fails on missing values, unresolved environment placeholders, and
  invalid project, dataset, bucket, region, or relation identifiers.
- Existing Favorita configuration remains the reference adapter while consumers migrate to the
  catalog in subsequent phases.
- Frequency abstraction and extension-provider APIs remain separate changes with their own
  compatibility evidence.

## Consequences

New projects receive an explicit, reviewable resource boundary and CI can validate it without
cloud access. This does not yet make every runtime path generic: legacy scripts and model configs
still contain Favorita defaults until they are migrated behind the catalog. The phased approach
preserves accepted forecasts and makes remaining hard-coded paths measurable.

## Related decisions and specifications

- [General-purpose platform specification](../specs/platform_generalization.md)
- [Terraform modules specification](../specs/terraform_modules.md)
- [Reference architecture](../reference_architecture.md)
