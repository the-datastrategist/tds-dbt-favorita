import pandas as pd
import pytest

from vertex.models.xgboost.direct_multi_horizon import (
    target_columns_by_horizon,
    validate_complete_horizon_batch,
)


def test_target_mapping_must_match_declared_horizons():
    inputs = {
        "prediction_horizons": [1, 2, 3],
        "target_columns_by_horizon": {1: "n1", 2: "n2", 3: "n3"},
    }
    assert target_columns_by_horizon(inputs) == {1: "n1", 2: "n2", 3: "n3"}
    inputs["target_columns_by_horizon"].pop(2)
    with pytest.raises(ValueError, match="must match"):
        target_columns_by_horizon(inputs)


def test_complete_batch_requires_every_horizon_per_entity():
    rows = pd.DataFrame(
        [
            {"store_nbr": store, "forecast_horizon": horizon}
            for store in (1, 2)
            for horizon in range(1, 8)
        ]
    )
    validate_complete_horizon_batch(rows, horizons=list(range(1, 8)), entity_columns=["store_nbr"])
    with pytest.raises(ValueError, match="every configured horizon"):
        validate_complete_horizon_batch(
            rows.iloc[:-1], horizons=list(range(1, 8)), entity_columns=["store_nbr"]
        )


def test_complete_batch_rejects_duplicate_entity_horizon():
    rows = pd.DataFrame([{"store_nbr": 1, "forecast_horizon": horizon} for horizon in range(1, 8)])
    with pytest.raises(ValueError, match="duplicate"):
        validate_complete_horizon_batch(
            pd.concat([rows, rows.iloc[[0]]], ignore_index=True),
            horizons=list(range(1, 8)),
            entity_columns=["store_nbr"],
        )
