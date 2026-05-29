"""Tests for config-driven data loading."""

import pytest

from vertex.utils.data_loading import load_data_from_config


@pytest.mark.unit
class TestLoadDataFromConfig:
    def test_rejects_unsafe_source_table(self):
        config = {"inputs": {"source_table": "dataset.table; DROP TABLE secrets"}}
        with pytest.raises(ValueError, match="Invalid BigQuery"):
            load_data_from_config(config)
