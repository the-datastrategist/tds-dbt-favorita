"""Tests for configured canonical hierarchy materialization."""

import pytest

from scripts.materialize_hierarchy import build_materialization_sql
from vertex.config.hierarchy import validate_hierarchy_config


@pytest.mark.unit
def test_materialization_uses_canonical_identity_and_configured_levels() -> None:
    config = validate_hierarchy_config(
        {
            "hierarchy": {
                "name": "retail",
                "version": "v2",
                "source": {
                    "relation": "forecast_features_store",
                    "entity_key_json_column": "entity_key_json",
                    "effective_from": "2026-01-01",
                },
                "levels": [
                    {"name": "company", "keys": []},
                    {"name": "region", "keys": ["region_id"]},
                    {"name": "store", "keys": ["region_id", "store_id"]},
                ],
                "reconciliation": {"method": "bottom_up"},
            }
        }
    )

    sql = build_materialization_sql(config, table_prefix="project.dataset")

    assert "`project.dataset.forecast_features_store`" in sql
    assert "JSON_VALUE(entity_key_json, '$.region_id')" in sql
    assert "JSON_VALUE(entity_key_json, '$.store_id')" in sql
    assert "JSON_QUERY(entity_key_json, '$.store_id')" in sql
    assert "'company:all'" in sql
    assert "PARTITION BY node_id" in sql
    assert "PARTITION BY parent_node_id, child_node_id" in sql
    assert "UNION DISTINCT" not in sql
    assert "int_sales_store_daily" not in sql
    assert "store_nbr" not in sql
