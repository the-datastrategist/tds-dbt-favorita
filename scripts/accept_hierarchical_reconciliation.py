#!/usr/bin/env python3
"""Validate one live hierarchy-enabled forecast draft and emit acceptance evidence."""

from __future__ import annotations

import argparse
import json
import re
from typing import Any

import pandas as pd

from vertex.config.forecast_contract import load_forecast_contract
from vertex.config.hierarchy import load_hierarchy_config
from vertex.evaluation.reconciliation import (
    build_hierarchy_graph,
    coherence_violations,
    reconcile_forecasts,
)
from vertex.utils.bigquery_utils import run_query

DEFAULT_CONTRACT = "vertex/config/forecast_contract_hierarchical_publication.yaml"
DEFAULT_HIERARCHY = "vertex/config/hierarchy.yaml"
DEFAULT_TABLE_PREFIX = "tds-favorita.favorita"
RUN_ID_PATTERN = re.compile(r"^[a-f0-9]{64}$")
QUANTILE_COLUMNS = {0.1: "prediction_p10", 0.5: "prediction_p50", 0.9: "prediction_p90"}


def _load_live_rows(
    *, forecast_run_id: str, table_prefix: str, project_id: str
) -> tuple[pd.DataFrame, ...]:
    nodes = run_query(
        f"""
        SELECT * FROM `{table_prefix}.forecast_hierarchy_nodes`
        WHERE hierarchy_name = 'favorita_demand' AND hierarchy_version = 'v1'
        """,
        project_id=project_id,
    )
    edges = run_query(
        f"""
        SELECT * FROM `{table_prefix}.forecast_hierarchy_edges`
        WHERE hierarchy_name = 'favorita_demand' AND hierarchy_version = 'v1'
        """,
        project_id=project_id,
    )
    outputs = run_query(
        f"""
        SELECT * FROM `{table_prefix}.forecast_outputs`
        WHERE forecast_run_id = '{forecast_run_id}'
        """,
        project_id=project_id,
    )
    runs = run_query(
        f"""
        SELECT * FROM `{table_prefix}.forecast_runs`
        WHERE forecast_run_id = '{forecast_run_id}'
        """,
        project_id=project_id,
    )
    reconciliation_runs = run_query(
        f"""
        SELECT * FROM `{table_prefix}.forecast_reconciliation_runs`
        WHERE forecast_run_id = '{forecast_run_id}'
        """,
        project_id=project_id,
    )
    reconciliation_outputs = run_query(
        f"""
        SELECT * FROM `{table_prefix}.forecast_reconciled_outputs`
        WHERE forecast_run_id = '{forecast_run_id}'
        """,
        project_id=project_id,
    )
    metrics = run_query(
        f"""
        SELECT * FROM `{table_prefix}.forecast_reconciliation_metrics`
        WHERE hierarchy_name = 'favorita_demand'
          AND hierarchy_version = 'v1'
          AND model_config_name = 'favorita_store_h7_xgboost'
        """,
        project_id=project_id,
    )
    return (
        nodes,
        edges,
        outputs,
        runs,
        reconciliation_runs,
        reconciliation_outputs,
        metrics,
    )


def run_acceptance(
    *,
    forecast_run_id: str,
    project_id: str,
    table_prefix: str = DEFAULT_TABLE_PREFIX,
    contract_path: str = DEFAULT_CONTRACT,
    hierarchy_path: str = DEFAULT_HIERARCHY,
) -> dict[str, Any]:
    if not RUN_ID_PATTERN.fullmatch(forecast_run_id):
        raise ValueError("forecast run id must be a 64-character lowercase hex digest")
    contract = load_forecast_contract(contract_path)
    hierarchy = load_hierarchy_config(hierarchy_path)
    declared_levels = [level["name"] for level in hierarchy.levels]
    if contract.spec["hierarchy"] != declared_levels:
        raise RuntimeError("contract hierarchy does not match the pinned hierarchy config")
    if contract.reconciliation_policy != hierarchy.method:
        raise RuntimeError("contract reconciliation method does not match hierarchy config")
    unknown_quantiles = sorted(set(contract.quantiles).difference(QUANTILE_COLUMNS))
    if unknown_quantiles:
        raise RuntimeError(f"canonical output has no columns for quantiles {unknown_quantiles}")

    (
        nodes,
        edges,
        outputs,
        runs,
        reconciliation_runs,
        reconciliation_outputs,
        metrics,
    ) = _load_live_rows(
        forecast_run_id=forecast_run_id,
        table_prefix=table_prefix,
        project_id=project_id,
    )
    if outputs.empty or len(runs) != 1 or runs.iloc[0]["run_status"] != "draft":
        raise RuntimeError("accepted run must be one visible, non-empty draft")
    if len(reconciliation_runs) != 1:
        raise RuntimeError("accepted run must have exactly one reconciliation run record")
    graph = build_hierarchy_graph(nodes, edges)
    parent_counts = edges.groupby("child_node_id").size()
    if not parent_counts.eq(1).all():
        raise RuntimeError("every hierarchy child must have exactly one parent")

    output = outputs.copy()
    output["node_id"] = output["entity_key_json"].map(
        lambda value: str((value if isinstance(value, dict) else json.loads(value))["node_id"])
    )
    output_nodes = set(output["node_id"])
    orphan_nodes = sorted(output_nodes.difference(graph.nodes))
    missing_leaves = sorted(set(graph.leaves).difference(output_nodes))
    if orphan_nodes or missing_leaves:
        raise RuntimeError(
            f"hierarchy membership failed: orphan_nodes={orphan_nodes}, missing_leaves={missing_leaves}"
        )

    quantile_columns = [QUANTILE_COLUMNS[value] for value in contract.quantiles]
    missing_quantiles = int(output[quantile_columns].isna().any(axis=1).sum())
    invalid_order = int(
        (
            (output["prediction_p10"] > output["prediction_p50"])
            | (output["prediction_p50"] > output["prediction_p90"])
        ).sum()
    )
    lineage_fields = ["hierarchy_version", "reconciliation_method", "reconciliation_run_id"]
    missing_lineage = int(output[lineage_fields].isna().any(axis=1).sum())
    invalid_lineage = int(
        (
            (output["hierarchy_version"] != hierarchy.version)
            | (output["reconciliation_method"] != hierarchy.method)
        ).sum()
    )
    reconciliation_rows = output.rename(
        columns={"forecast_origin": "forecast_origin", "target_date": "target_date"}
    )
    violations_by_quantile = {
        column: len(
            coherence_violations(
                reconciliation_rows,
                nodes,
                edges,
                value_column=column,
                tolerance_abs=hierarchy.tolerance_abs,
            )
        )
        for column in quantile_columns
    }
    if missing_quantiles or invalid_order or missing_lineage or invalid_lineage:
        raise RuntimeError("quantile or reconciliation lineage acceptance failed")
    if any(violations_by_quantile.values()):
        raise RuntimeError(f"hierarchical coherence failed: {violations_by_quantile}")

    expected_output_ids = set(output["forecast_output_id"].astype(str))
    linked_output_ids = set(reconciliation_outputs["forecast_output_id"].dropna().astype(str))
    base_columns = [f"base_{column}" for column in quantile_columns]
    separate_persistence_valid = (
        len(reconciliation_outputs) == len(output)
        and reconciliation_outputs["reconciliation_output_id"].nunique() == len(output)
        and linked_output_ids == expected_output_ids
        and not reconciliation_outputs[base_columns + quantile_columns].isna().any(axis=None)
    )
    if not separate_persistence_valid:
        raise RuntimeError("base and reconciled output persistence is incomplete or duplicated")
    required_metric_pairs = {
        (level, metric) for level in ("company", "store") for metric in ("mae", "wape")
    }
    observed_metric_pairs = set(zip(metrics["level_name"], metrics["metric_name"]))
    if not required_metric_pairs.issubset(observed_metric_pairs):
        raise RuntimeError("level-wise base-versus-reconciled metrics are incomplete")
    if metrics["reconciliation_metric_id"].nunique() != len(metrics):
        raise RuntimeError("reconciliation metrics contain duplicate logical records")

    # Fail-closed probe: a duplicate parent assignment must stop reconciliation before rows exist
    # for persistence. This exercises the same graph validation called by the scheduled stage.
    invalid_edges = pd.concat([edges, edges.iloc[[0]]], ignore_index=True)
    failure_probe_blocked = False
    failure_probe_error = None
    try:
        reconcile_forecasts(output, nodes, invalid_edges, method=hierarchy.method)
    except ValueError as exc:
        failure_probe_blocked = True
        failure_probe_error = str(exc)
    if not failure_probe_blocked:
        raise RuntimeError("invalid reconciliation graph did not fail closed")

    return {
        "forecast_run_id": forecast_run_id,
        "run_status": str(runs.iloc[0]["run_status"]),
        "forecast_contract_name": contract.name,
        "forecast_contract_hash": contract.hash,
        "hierarchy_name": hierarchy.name,
        "hierarchy_version": hierarchy.version,
        "hierarchy_hash": hierarchy.hash,
        "reconciliation_method": hierarchy.method,
        "tolerance_abs": hierarchy.tolerance_abs,
        "configured_quantiles": contract.quantiles,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "root_count": len(graph.roots),
        "leaf_count": len(graph.leaves),
        "output_row_count": len(output),
        "children_with_exactly_one_parent": int(parent_counts.eq(1).sum()),
        "orphan_forecast_node_count": len(orphan_nodes),
        "missing_eligible_leaf_count": len(missing_leaves),
        "missing_quantile_row_count": missing_quantiles,
        "invalid_quantile_order_count": invalid_order,
        "coherence_violations_by_quantile": violations_by_quantile,
        "missing_reconciliation_lineage_count": missing_lineage,
        "invalid_reconciliation_lineage_count": invalid_lineage,
        "reconciliation_run_record_count": len(reconciliation_runs),
        "reconciliation_output_record_count": len(reconciliation_outputs),
        "distinct_reconciliation_output_id_count": int(
            reconciliation_outputs["reconciliation_output_id"].nunique()
        ),
        "linked_forecast_output_id_count": len(linked_output_ids),
        "base_and_reconciled_values_separately_queryable": separate_persistence_valid,
        "reconciliation_metric_record_count": len(metrics),
        "reconciliation_metric_levels": sorted(metrics["level_name"].unique().tolist()),
        "reconciliation_metric_names": sorted(metrics["metric_name"].unique().tolist()),
        "failure_probe_blocked": failure_probe_blocked,
        "failure_probe_error": failure_probe_error,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--forecast-run-id", required=True)
    parser.add_argument("--project-id", default="tds-favorita")
    parser.add_argument("--table-prefix", default=DEFAULT_TABLE_PREFIX)
    parser.add_argument("--contract-path", default=DEFAULT_CONTRACT)
    parser.add_argument("--hierarchy-path", default=DEFAULT_HIERARCHY)
    args = parser.parse_args()
    print(json.dumps(run_acceptance(**vars(args)), indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
