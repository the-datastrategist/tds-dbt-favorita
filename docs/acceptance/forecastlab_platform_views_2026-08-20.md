# ForecastLab platform-view acceptance — 2026-08-20

## Result

**Accepted for authenticated read-only use.** Pipeline Health and Hierarchy/Reconciliation are
live on the private ForecastLab service. Lifecycle mutations and publication webhooks remain
disabled; this record does not authorize or claim controlled mutation acceptance.

## Deployment evidence

| Field | Accepted value |
|---|---|
| Project / region | `tds-favorita` / `us-central1` |
| Service | `forecast-retrieval-api` |
| Revision | `forecast-retrieval-api-00008-25h` |
| Image digest | `sha256:3034dbe2199b1b99912a509397e9ae73b60922b35c8ed61c533c58b7a00f3e36` |
| Traffic | 100% to the ready revision |
| Authorization | IAP; one named member; no public binding |
| Mutation mode | Disabled |

The fail-closed Terraform plan gate passed with one in-place image update and no create or destroy
actions. The sanitized live gate passed with an anonymous HTTP 302 sign-in redirect, immutable
image pinning, authorization enabled, and mutations disabled.

## Pipeline Health evidence

The authenticated `/pipeline` route loaded two persisted pipeline runs. The selected hierarchical
publication run showed:

- stages `score`, `route`, `calibrate`, `reconcile`, and `validate` in positions 1–5;
- 55 persisted outputs, one horizon, and zero missing quantiles;
- zero failed blocking gates;
- passing point-in-time cutoff, prediction completeness, and quantile-ordering checks; and
- explicit “unavailable” display for historical candidate and eligibility counts rather than a
  fabricated zero or server error.

The nullable-count behavior was regression tested after live warehouse validation exposed legacy
rows without candidate and eligibility evidence.

## Hierarchy evidence

The authenticated `/hierarchy` route loaded hierarchy `favorita_demand` version `v1`, reconciliation
run `aff1ca0133224082a6b512aa329bc55f0d4403d4bfdd804e00e09b36e2291f16`:

- bottom-up reconciliation completed with tolerance `0.01`;
- 55 nodes, 54 edges, and two levels were present;
- every non-root node had exactly one parent;
- the hierarchy was acyclic;
- child totals were coherent;
- every quantile was reconciled; and
- reconciled quantiles remained ordered.

All five gates reported zero violations, and the browser console contained no errors.

## Rollback

Roll back to revision `forecast-retrieval-api-00006-2pp` or its accepted immutable image if the new
revision loses IAP, warehouse-read capability, or route stability. Preserve private IAM and keep
mutations disabled during rollback.
