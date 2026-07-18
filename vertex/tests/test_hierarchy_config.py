"""Tests for hierarchy configuration."""

import pytest

from vertex.config.hierarchy import validate_hierarchy_config


def _config(method: str = "bottom_up") -> dict:
    return {
        "hierarchy": {
            "name": "retail",
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
