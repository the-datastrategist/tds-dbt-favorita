"""Pytest configuration and fixtures."""

import os

import pytest


@pytest.fixture
def sample_dataframe():
    """Fixture providing a sample DataFrame for testing."""
    import pandas as pd

    dates = pd.date_range(start="2023-01-01", end="2023-01-31", freq="D")
    return pd.DataFrame(
        {
            "date": dates,
            "value": range(len(dates)),
            "category": ["A", "B"] * (len(dates) // 2) + ["A"] * (len(dates) % 2),
        }
    )


@pytest.fixture
def temp_config_file():
    """Fixture providing a temporary config file."""
    import tempfile

    import yaml

    config = {
        "configs": [
            {
                "name": "test_config",
                "inputs": {
                    "project_id": "test-project",
                    "region": "us-central1",
                    "sql_query": "SELECT * FROM test_table",
                },
            }
        ]
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(config, f)
        temp_path = f.name

    yield temp_path

    # Cleanup
    if os.path.exists(temp_path):
        os.unlink(temp_path)
