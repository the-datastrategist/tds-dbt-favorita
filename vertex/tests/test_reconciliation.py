"""Tests for coherent hierarchical forecast reconciliation."""

import pandas as pd
import pytest

from vertex.evaluation.reconciliation import (
    build_hierarchy_graph,
    coherence_violations,
    reconcile_forecasts,
    reconcile_values,
)


@pytest.fixture
def hierarchy():
    nodes = pd.DataFrame(
        {
            "node_id": ["company", "store_1", "store_2", "sku_1", "sku_2", "sku_3"],
            "level_name": ["company", "store", "store", "sku", "sku", "sku"],
        }
    )
    edges = pd.DataFrame(
        {
            "parent_node_id": ["company", "company", "store_1", "store_1", "store_2"],
            "child_node_id": ["store_1", "store_2", "sku_1", "sku_2", "sku_3"],
            "allocation_weight": [0.6, 0.4, 0.25, 0.75, 1.0],
        }
    )
    return nodes, edges


@pytest.mark.unit
def test_graph_rejects_multiple_parents(hierarchy):
    nodes, edges = hierarchy
    duplicate_parent = pd.concat(
        [
            edges,
            pd.DataFrame({"parent_node_id": ["store_2"], "child_node_id": ["sku_1"]}),
        ],
        ignore_index=True,
    )
    with pytest.raises(ValueError, match="one parent"):
        build_hierarchy_graph(nodes, duplicate_parent)


@pytest.mark.unit
def test_bottom_up_aggregates_leaf_forecasts(hierarchy):
    nodes, edges = hierarchy
    graph = build_hierarchy_graph(nodes, edges)
    base = {node: 999.0 for node in graph.nodes}
    base.update({"sku_1": 10.0, "sku_2": 30.0, "sku_3": 20.0})
    result = reconcile_values(base, graph, method="bottom_up")
    assert result["store_1"] == 40.0
    assert result["store_2"] == 20.0
    assert result["company"] == 60.0


@pytest.mark.unit
def test_top_down_uses_configured_allocation_weights(hierarchy):
    nodes, edges = hierarchy
    graph = build_hierarchy_graph(nodes, edges)
    weights = {
        (row.parent_node_id, row.child_node_id): row.allocation_weight for row in edges.itertuples()
    }
    result = reconcile_values(
        {node: 100.0 for node in graph.nodes}, graph, method="top_down", weights=weights
    )
    assert result == {
        "company": 100.0,
        "store_1": 60.0,
        "sku_1": 15.0,
        "sku_2": 45.0,
        "store_2": 40.0,
        "sku_3": 40.0,
    }


@pytest.mark.unit
def test_middle_out_preserves_anchor_forecasts(hierarchy):
    nodes, edges = hierarchy
    graph = build_hierarchy_graph(nodes, edges)
    weights = {
        (row.parent_node_id, row.child_node_id): row.allocation_weight for row in edges.itertuples()
    }
    base = {node: 0.0 for node in graph.nodes}
    base.update({"store_1": 80.0, "store_2": 20.0})
    result = reconcile_values(
        base, graph, method="middle_out", middle_level="store", weights=weights
    )
    assert result["company"] == 100.0
    assert result["sku_1"] == 20.0
    assert result["sku_2"] == 60.0
    assert result["sku_3"] == 20.0


@pytest.mark.unit
def test_mint_produces_coherent_weighted_projection(hierarchy):
    nodes, edges = hierarchy
    graph = build_hierarchy_graph(nodes, edges)
    base = {
        "company": 75.0,
        "store_1": 50.0,
        "sku_1": 10.0,
        "sku_2": 30.0,
        "store_2": 30.0,
        "sku_3": 20.0,
    }
    result = reconcile_values(base, graph, method="mint")
    assert result["company"] == pytest.approx(result["store_1"] + result["store_2"])
    assert result["store_1"] == pytest.approx(result["sku_1"] + result["sku_2"])
    assert result["store_2"] == pytest.approx(result["sku_3"])


@pytest.mark.unit
def test_dataframe_reconciliation_preserves_base_and_has_no_violations(hierarchy):
    nodes, edges = hierarchy
    rows = []
    for node, value in zip(nodes["node_id"], [100, 60, 40, 10, 30, 20]):
        rows.append(
            {
                "node_id": node,
                "forecast_origin": "2026-01-01",
                "target_date": "2026-01-02",
                "horizon": 1,
                "prediction_p10": value * 0.8,
                "prediction_p50": value,
                "prediction_p90": value * 1.2,
            }
        )
    result = reconcile_forecasts(pd.DataFrame(rows), nodes, edges, method="bottom_up")
    assert "base_prediction_p50" in result
    assert result["reconciliation_method"].eq("bottom_up").all()
    assert coherence_violations(result, nodes, edges).empty
