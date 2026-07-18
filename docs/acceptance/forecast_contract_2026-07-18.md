# Forecast contract and canonical output acceptance — 2026-07-18

The canonical forecast contract passed live GCP persistence, publication, and warehouse
validation on 2026-07-18.

## Accepted run

| Evidence | Value |
|---|---|
| Source prediction run | `c8dc2574ad4dd89cb64a62aeaa82c20deee48f672fdaf32826249c4008e9d214` |
| Canonical forecast run | `494af1eaa147c349f5b334bca1af11f5e74573c4500cbde5b76ccb20fb6cabb2` |
| Implementation commit | `9b0508a4122f4519788252a0637bfdb59daf598c` |
| Model | `favorita_store_h7_xgboost` |
| Horizon | 7 days |
| Source/canonical/entity rows | 51 / 51 / 51 |
| Approval/publication rows | 51 / 51 |
| Publication mode | `auto_publish` |

The acceptance command reported zero invalid horizons, invalid quantile ordering, missing
provenance, and missing delivery statuses. All rows were written through the standard canonical
writer and publication lifecycle—not by direct acceptance-only inserts.

## Warehouse validation

The additive DDL migration introduced `contract_enforced`. New hardened writes set it to true;
legacy append-only history is retained and exposed as false by `stg_forecast_outputs`.

The nine forecast staging views built successfully. Their complete test selection passed 107 data
tests (`PASS=109`, including two hooks; `WARN=0`, `ERROR=0`). This includes:

- canonical uniqueness and target-date/horizon consistency;
- registered contract and forecast-run relationships;
- required provenance, routing confidence, and lifecycle status;
- approval, publication, override, exception, revision, and status-history relationships;
- composite retry safety for batch idempotency key plus forecast output.

## Reproduce

```bash
make vertex-forecast-contract-accept \
  VERTEX_FORECAST_SOURCE_RUN_ID=c8dc2574ad4dd89cb64a62aeaa82c20deee48f672fdaf32826249c4008e9d214
```

The command reapplies idempotent DDL, persists the configured horizon-7 batch, runs automatic
approval and publication, and fails if any acceptance invariant is violated.
