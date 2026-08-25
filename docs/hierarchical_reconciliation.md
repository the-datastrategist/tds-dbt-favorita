# Hierarchical reconciliation operator guide

Hierarchical reconciliation makes forecasts coherent across configured aggregation levels. In
the reference Favorita implementation, 54 store forecasts roll up to one company forecast. A
published company value therefore equals the sum of its eligible stores for every target date and
configured quantile.

## Base and reconciled forecasts

A base forecast is the calibrated prediction entering reconciliation. A reconciled forecast is
the value after applying the configured hierarchy method. The platform never overwrites the base
value: `forecast_reconciled_outputs` stores both value sets and links them to the canonical
`forecast_outputs` row. `forecast_reconciliation_runs` records the hierarchy version, method,
input fingerprint, and execution result.

Both output tables preserve `series_key`, `entity_key_json`, and `target_timestamp`, so
reconciliation evidence uses the same series and temporal identity as scoring and publication.
The daily `target_date` field remains available as a compatibility projection.

## Configuration

The reference graph is pinned by `vertex/config/hierarchy.yaml`; the scheduled contract is
`vertex/config/forecast_contract_hierarchical_publication.yaml`. The contract's hierarchy levels
and reconciliation method must exactly match the hierarchy file. Nodes and edges are versioned in
BigQuery so a historical run always retains its original graph semantics.

The hierarchy file also declares a canonical source relation, its `entity_key_json` column, and
an effective date. `make vertex-hierarchy-materialize` derives every configured level and edge
from those opaque canonical identities; project-specific source columns do not enter the
reconciliation runtime. Use `HIERARCHY_CONFIG_PATH=<path>` to select a different hierarchy file.

Supported methods are:

- `bottom_up`: retain leaf forecasts and aggregate them upward. This is the reference default.
- `top_down`: allocate a parent forecast using configured or historical proportions.
- `middle_out`: retain a configured middle level, aggregate upward, and allocate downward.
- `mint`: use residual covariance to minimize reconciliation error when enough backtest evidence
  exists.

Use bottom-up when leaf forecasts are trustworthy and complete. Use allocation methods when the
aggregate forecast is stronger or leaf evidence is sparse. Use MinT only with stable,
representative residual covariance.

## Run and verify

Apply the DDL and hierarchy graph, then execute the scheduled hierarchy-aware contract:

```bash
make vertex-bq-ddl
make vertex-hierarchy-materialize
make prefect-flow-scheduled-forecast \
  CONTRACT_PATH=vertex/config/forecast_contract_hierarchical_publication.yaml \
  HIERARCHY_CONFIG_PATH=vertex/config/hierarchy.yaml
```

Verify an immutable live run with:

```bash
make vertex-hierarchy-accept FORECAST_RUN_ID=<64-character-run-id>
```

The acceptance command verifies graph structure, eligible leaf membership, configured quantile
coverage and ordering, parent-child coherence within tolerance, required lineage, one-to-one
base/reconciled persistence, level-wise metrics, and fail-closed behavior.

To evaluate backtest predictions at each hierarchy level:

```bash
make vertex-hierarchy-backtest \
  BACKTEST_RUN_ID=<backtest-run-id> \
  MODEL_CONFIG=favorita_store_h7_xgboost
```

This writes append-only base-versus-reconciled MAE and WAPE records by hierarchy level and
horizon. Re-running the same logical evaluation is idempotent.

## Publication safety

Reconciliation is the final numerical transformation after calibration and before validation.
Every configured quantile must be coherent and maintain `P10 <= P50 <= P90`. Invalid graphs,
orphan nodes, missing eligible leaves, tolerance violations, or incomplete lineage are blocking
errors. The pipeline persists the visible draft record last, so a reconciliation failure cannot
expose partial canonical output.

Live reference evidence is recorded in
[hierarchical reconciliation acceptance](acceptance/hierarchical_reconciliation_2026-08-07.md).
