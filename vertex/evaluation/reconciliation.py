"""Coherent hierarchical forecast reconciliation."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Sequence

import numpy as np
import pandas as pd

from vertex.utils.data_utils import get_hash


@dataclass(frozen=True)
class HierarchyGraph:
    """Validated hierarchy graph ordered from roots to leaves."""

    nodes: tuple[str, ...]
    parent_by_child: dict[str, str]
    level_by_node: dict[str, str]
    children_by_parent: dict[str, tuple[str, ...]]
    roots: tuple[str, ...]
    leaves: tuple[str, ...]


def _node_key(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("hierarchy node_key_json must be a JSON object")


def expand_leaf_predictions(
    predictions: pd.DataFrame,
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    *,
    leaf_keys: Sequence[str],
    group_columns: Sequence[str] = ("date", "forecast_date", "forecast_horizon"),
) -> pd.DataFrame:
    """Map model leaf rows to nodes and synthesize auditable ancestor base forecasts."""
    graph = build_hierarchy_graph(nodes, edges)
    required = {"prediction", *leaf_keys, *group_columns}
    if missing := sorted(required.difference(predictions.columns)):
        raise ValueError(f"leaf predictions are missing required columns: {missing}")
    node_keys = {
        str(row.node_id): _node_key(row.node_key_json)
        for row in nodes[["node_id", "node_key_json"]].itertuples(index=False)
    }
    leaf_by_key = {
        tuple(node_keys[node].get(key) for key in leaf_keys): node for node in graph.leaves
    }
    work = predictions.copy()
    work["node_id"] = [
        leaf_by_key.get(tuple(row[key] for key in leaf_keys)) for _, row in work.iterrows()
    ]
    if work["node_id"].isna().any():
        missing_keys = work.loc[work["node_id"].isna(), list(leaf_keys)].drop_duplicates()
        raise ValueError(
            "eligible predictions have no hierarchy leaf: "
            f"{missing_keys.to_dict(orient='records')[:5]}"
        )

    descendants = {node: _descendant_leaves(graph, node) for node in graph.nodes}
    output: list[pd.DataFrame] = []
    for _, group in work.groupby(list(group_columns), dropna=False, sort=False):
        if group["node_id"].duplicated().any():
            raise ValueError("leaf prediction groups must contain one row per hierarchy node")
        present = set(group["node_id"].astype(str))
        missing_leaves = sorted(set(graph.leaves).difference(present))
        if missing_leaves:
            raise ValueError(
                f"hierarchy leaves have no eligible prediction rows: {missing_leaves[:5]}"
            )
        rows = [group]
        for node in graph.nodes:
            if node in graph.leaves:
                continue
            child_rows = group[group["node_id"].isin(descendants[node])]
            aggregate = child_rows.iloc[[0]].copy()
            aggregate["node_id"] = node
            aggregate["prediction"] = float(child_rows["prediction"].sum())
            aggregate["prediction_id"] = get_hash(
                {
                    "node_id": node,
                    **{column: str(aggregate.iloc[0][column]) for column in group_columns},
                    "source_prediction_ids": sorted(child_rows["prediction_id"].astype(str)),
                }
            )
            rows.append(aggregate)
        output.append(pd.concat(rows, ignore_index=True))
    return pd.concat(output, ignore_index=True)


def build_hierarchy_graph(nodes: pd.DataFrame, edges: pd.DataFrame) -> HierarchyGraph:
    """Validate nodes and edges and return an acyclic single-parent graph."""
    node_required = {"node_id", "level_name"}
    edge_required = {"parent_node_id", "child_node_id"}
    if missing := sorted(node_required.difference(nodes.columns)):
        raise ValueError(f"nodes are missing required columns: {missing}")
    if missing := sorted(edge_required.difference(edges.columns)):
        raise ValueError(f"edges are missing required columns: {missing}")
    if nodes["node_id"].isna().any() or nodes["node_id"].duplicated().any():
        raise ValueError("node_id must be non-null and unique")
    node_ids = tuple(nodes["node_id"].astype(str))
    known = set(node_ids)
    normalized_edges = edges[["parent_node_id", "child_node_id"]].astype(str)
    referenced = set(normalized_edges.stack())
    if unknown := sorted(referenced.difference(known)):
        raise ValueError(f"edges reference unknown nodes: {unknown}")
    if (normalized_edges["parent_node_id"] == normalized_edges["child_node_id"]).any():
        raise ValueError("hierarchy edges cannot be self-referential")
    if normalized_edges["child_node_id"].duplicated().any():
        raise ValueError("every hierarchy child must have exactly one parent")

    parent_by_child = dict(
        zip(normalized_edges["child_node_id"], normalized_edges["parent_node_id"])
    )
    children: dict[str, list[str]] = defaultdict(list)
    for child, parent in parent_by_child.items():
        children[parent].append(child)
    roots = tuple(node for node in node_ids if node not in parent_by_child)
    if not roots:
        raise ValueError("hierarchy graph has no root")
    visited: set[str] = set()
    active: set[str] = set()

    def visit(node: str) -> None:
        if node in active:
            raise ValueError("hierarchy graph contains a cycle")
        if node in visited:
            return
        active.add(node)
        for child in children.get(node, []):
            visit(child)
        active.remove(node)
        visited.add(node)

    for root in roots:
        visit(root)
    if visited != known:
        raise ValueError("hierarchy graph contains an unreachable cycle")
    ordered_nodes: list[str] = []

    def order(node: str) -> None:
        ordered_nodes.append(node)
        for child in children.get(node, []):
            order(child)

    for root in roots:
        order(root)
    leaves = tuple(node for node in ordered_nodes if not children.get(node))
    return HierarchyGraph(
        nodes=tuple(ordered_nodes),
        parent_by_child=parent_by_child,
        level_by_node=dict(zip(nodes["node_id"].astype(str), nodes["level_name"].astype(str))),
        children_by_parent={key: tuple(value) for key, value in children.items()},
        roots=roots,
        leaves=leaves,
    )


def _descendant_leaves(graph: HierarchyGraph, node: str) -> tuple[str, ...]:
    children = graph.children_by_parent.get(node, ())
    if not children:
        return (node,)
    return tuple(leaf for child in children for leaf in _descendant_leaves(graph, child))


def _summing_matrix(graph: HierarchyGraph) -> np.ndarray:
    return np.asarray(
        [
            [float(leaf in _descendant_leaves(graph, node)) for leaf in graph.leaves]
            for node in graph.nodes
        ]
    )


def _normalized_child_weights(
    graph: HierarchyGraph, weights: dict[tuple[str, str], float] | None
) -> dict[tuple[str, str], float]:
    result: dict[tuple[str, str], float] = {}
    for parent, children in graph.children_by_parent.items():
        raw = np.asarray(
            [max(0.0, float((weights or {}).get((parent, child), 1.0))) for child in children]
        )
        if raw.sum() == 0:
            raw = np.ones(len(children))
        for child, value in zip(children, raw / raw.sum()):
            result[(parent, child)] = float(value)
    return result


def _aggregate_up(values: dict[str, float], graph: HierarchyGraph) -> None:
    for node in reversed(graph.nodes):
        children = graph.children_by_parent.get(node, ())
        if children:
            values[node] = float(sum(values[child] for child in children))


def _allocate_down(
    values: dict[str, float],
    graph: HierarchyGraph,
    anchors: Sequence[str],
    weights: dict[tuple[str, str], float],
) -> None:
    def allocate(parent: str) -> None:
        for child in graph.children_by_parent.get(parent, ()):
            values[child] = values[parent] * weights[(parent, child)]
            allocate(child)

    for anchor in anchors:
        allocate(anchor)


def reconcile_values(
    base_values: dict[str, float],
    graph: HierarchyGraph,
    *,
    method: str,
    weights: dict[tuple[str, str], float] | None = None,
    middle_level: str | None = None,
    residual_variances: dict[str, float] | None = None,
) -> dict[str, float]:
    """Reconcile one forecast vector using the selected coherent method."""
    missing = sorted(set(graph.nodes).difference(base_values))
    if missing:
        raise ValueError(f"base forecasts are missing hierarchy nodes: {missing}")
    values = {node: float(base_values[node]) for node in graph.nodes}
    if method == "bottom_up":
        _aggregate_up(values, graph)
        return values
    child_weights = _normalized_child_weights(graph, weights)
    if method == "top_down":
        _allocate_down(values, graph, graph.roots, child_weights)
        return values
    if method == "middle_out":
        if not middle_level:
            raise ValueError("middle_out requires middle_level")
        anchors = tuple(node for node in graph.nodes if graph.level_by_node[node] == middle_level)
        if not anchors:
            raise ValueError(f"middle level {middle_level!r} has no hierarchy nodes")
        _allocate_down(values, graph, anchors, child_weights)
        _aggregate_up(values, graph)
        return values
    if method == "mint":
        summing = _summing_matrix(graph)
        variances = np.asarray(
            [max(float((residual_variances or {}).get(node, 1.0)), 1e-12) for node in graph.nodes]
        )
        inverse_covariance = np.diag(1.0 / variances)
        projection = summing @ np.linalg.pinv(summing.T @ inverse_covariance @ summing)
        projection = projection @ summing.T @ inverse_covariance
        reconciled = projection @ np.asarray([values[node] for node in graph.nodes])
        return dict(zip(graph.nodes, reconciled.astype(float)))
    raise ValueError(f"unsupported reconciliation method: {method!r}")


def reconcile_forecasts(
    forecasts: pd.DataFrame,
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    *,
    method: str,
    value_columns: Sequence[str] = ("prediction_p10", "prediction_p50", "prediction_p90"),
    group_columns: Sequence[str] = ("forecast_origin", "target_date", "horizon"),
    middle_level: str | None = None,
    residual_variances: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Reconcile every origin/target/horizon group and preserve base forecasts."""
    graph = build_hierarchy_graph(nodes, edges)
    required = {"node_id", *group_columns, *value_columns}
    if missing := sorted(required.difference(forecasts.columns)):
        raise ValueError(f"forecasts are missing required columns: {missing}")
    edge_weights = None
    if "allocation_weight" in edges.columns:
        edge_weights = {
            (str(row.parent_node_id), str(row.child_node_id)): float(row.allocation_weight)
            for row in edges.itertuples()
            if pd.notna(row.allocation_weight)
        }
    output: list[pd.DataFrame] = []
    for _, group in forecasts.groupby(list(group_columns), dropna=False, sort=False):
        if group["node_id"].astype(str).duplicated().any():
            raise ValueError("forecast groups must contain one row per hierarchy node")
        indexed = group.copy()
        indexed["node_id"] = indexed["node_id"].astype(str)
        indexed = indexed.set_index("node_id")
        for column in value_columns:
            indexed[f"base_{column}"] = indexed[column]
            reconciled = reconcile_values(
                indexed[column].astype(float).to_dict(),
                graph,
                method=method,
                weights=edge_weights,
                middle_level=middle_level,
                residual_variances=residual_variances,
            )
            indexed[column] = pd.Series(reconciled)
        reconciled_columns = list(value_columns)
        if (indexed[reconciled_columns].diff(axis=1).iloc[:, 1:] < 0).any(axis=None):
            raise ValueError(
                "reconciliation produced crossed quantiles; publication requires a joint "
                "coherent and monotonic solution"
            )
        indexed["reconciliation_method"] = method
        output.append(indexed.reset_index())
    return pd.concat(output, ignore_index=True) if output else forecasts.copy()


def coherence_violations(
    forecasts: pd.DataFrame,
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    *,
    value_column: str = "prediction_p50",
    group_columns: Sequence[str] = ("forecast_origin", "target_date", "horizon"),
    tolerance_abs: float = 0.01,
) -> pd.DataFrame:
    """Return parent rows whose value differs from the sum of direct children."""
    graph = build_hierarchy_graph(nodes, edges)
    violations: list[dict[str, object]] = []
    for group_key, group in forecasts.groupby(list(group_columns), dropna=False, sort=False):
        values = group.set_index(group["node_id"].astype(str))[value_column].astype(float).to_dict()
        keys = group_key if isinstance(group_key, tuple) else (group_key,)
        metadata = dict(zip(group_columns, keys))
        for parent, children in graph.children_by_parent.items():
            difference = values[parent] - sum(values[child] for child in children)
            if abs(difference) > tolerance_abs:
                violations.append({**metadata, "parent_node_id": parent, "difference": difference})
    return pd.DataFrame(violations)
