"""Tests for hierarchy configuration."""

import pandas as pd
import pytest

from vertex.config.hierarchy import validate_hierarchy_config
from vertex.evaluation.reconciliation import expand_leaf_predictions


def _config(method: str = "bottom_up") -> dict:
    return {
        "hierarchy": {
            "name": "retail",
            "source": {
                "relation": "forecast_features_store",
                "entity_key_json_column": "entity_key_json",
                "effective_from": "2026-01-01",
            },
            "levels": [
                {"name": "company", "keys": []},
                {"name": "store", "keys": ["store_id"]},
                {"name": "sku", "keys": ["store_id", "sku_id"]},
            ],
            "reconciliation": {"method": method, "tolerance_abs": 0.01},
        }
    }


@pytest.mark.unit
def test_validates_nested_hierarchy_config():
    config = validate_hierarchy_config(_config())
    assert config.name == "retail"
    assert config.method == "bottom_up"
    assert config.tolerance_abs == 0.01


@pytest.mark.unit
def test_rejects_level_that_drops_parent_keys():
    raw = _config()
    raw["hierarchy"]["levels"][2]["keys"] = ["sku_id"]
    with pytest.raises(ValueError, match="retain"):
        validate_hierarchy_config(raw)


@pytest.mark.unit
def test_middle_out_requires_middle_level():
    with pytest.raises(ValueError, match="middle_level"):
        validate_hierarchy_config(_config("middle_out"))


@pytest.mark.unit
def test_rejects_hierarchy_without_canonical_source():
    raw = _config()
    del raw["hierarchy"]["source"]

    with pytest.raises(ValueError, match="hierarchy.source"):
        validate_hierarchy_config(raw)


@pytest.mark.unit
def test_expands_store_predictions_to_company_node():
    predictions = pd.DataFrame(
        [
            {
                "prediction_id": f"p-{store_id}",
                "date": pd.Timestamp("2026-08-07"),
                "forecast_date": pd.Timestamp("2026-08-14"),
                "forecast_horizon": 7,
                "store_id": store_id,
                "prediction": value,
            }
            for store_id, value in ((1, 10.0), (2, 20.0))
        ]
    )
    nodes = pd.DataFrame(
        [
            {"node_id": "company:all", "level_name": "company", "node_key_json": "{}"},
            {"node_id": "store:1", "level_name": "store", "node_key_json": '{"store_id":1}'},
            {"node_id": "store:2", "level_name": "store", "node_key_json": '{"store_id":2}'},
        ]
    )
    edges = pd.DataFrame(
        [
            {"parent_node_id": "company:all", "child_node_id": "store:1"},
            {"parent_node_id": "company:all", "child_node_id": "store:2"},
        ]
    )

    expanded = expand_leaf_predictions(predictions, nodes, edges, leaf_keys=("store_id",))

    assert set(expanded["node_id"]) == {"company:all", "store:1", "store:2"}
    assert expanded.loc[expanded["node_id"] == "company:all", "prediction"].item() == 30.0
