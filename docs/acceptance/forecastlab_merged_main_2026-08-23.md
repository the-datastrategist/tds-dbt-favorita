# ForecastLab merged-main deployment — 2026-08-23

## Result

**Accepted for authenticated read-only use.** PR #57 was squash-merged as commit
`7b8fe367ce886d2ac2b08376401691ab7ddf96e5`, built from an isolated clean worktree, and deployed
without enabling lifecycle mutations or publication webhooks.

## Deployment evidence

| Field | Accepted value |
|---|---|
| Cloud Build | `2dcb472e-f619-49a3-a59d-d89d4184b8b4` |
| Image digest | `sha256:204d1ac6d50016abe3af4ba57637619d9183b8f06ee58e7a1a393378501f224b` |
| Cloud Run revision | `forecast-retrieval-api-00009-p6c` |
| Traffic | 100% to the ready revision |
| Container health | Passed; startup completed in 5.77 seconds |
| Authorization | IAP; one named member; no public access |
| Mutation mode | Disabled |
| Publication webhook | Disabled |

The Terraform plan contained zero additions, two in-place changes, and zero destructions: the
ForecastLab image update and the merged Artifact Registry description cleanup. Dataset-level API
access remained `roles/bigquery.dataViewer`; the lifecycle-role map remained empty.

## Live smoke evidence

- Anonymous `/pipeline` and `/hierarchy` requests each returned the expected IAP sign-in redirect.
- An authenticated browser loaded `/pipeline`, selected the persisted hierarchical publication
  run, and displayed all five ordered stages, 55 persisted outputs, zero blocking-gate failures,
  one horizon, and zero missing quantiles.
- The same authenticated session loaded `/hierarchy` with hierarchy version `v1`, 55 nodes, 54
  edges, two levels, bottom-up reconciliation, and zero failures across all five reconciliation
  gates.
- The browser console reported no errors on the hierarchy route.

## Rollback

Route traffic to ready revision `forecast-retrieval-api-00008-25h` if the merged-main revision
loses route stability or warehouse-read capability. Preserve IAP and keep lifecycle mutations and
publication webhooks disabled during rollback.
