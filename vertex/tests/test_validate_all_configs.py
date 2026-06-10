"""Validate model_config.yaml in CI."""

import pytest

from vertex.config.validate_all import validate_all_configs


@pytest.mark.unit
def test_validate_all_configs():
    names = validate_all_configs()
    assert "favorita_store_n1d_xgboost" in names
    assert len(names) >= 4
