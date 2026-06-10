"""Unit tests for ML pipeline resolution."""

from __future__ import annotations

import pytest

from orchestration.utils.pipelines import (
    list_pipeline_names,
    resolve_pipeline_config_names,
    resolve_pipeline_steps,
)


@pytest.mark.unit
def test_list_pipeline_names_includes_xgboost() -> None:
    names = list_pipeline_names()
    assert "favorita_xgboost" in names
    assert "favorita_arima" in names


@pytest.mark.unit
def test_resolve_pipeline_steps_xgboost_full() -> None:
    steps = resolve_pipeline_steps("favorita_xgboost")
    assert [s for s, _ in steps] == ["optimize", "train", "predict"]
    assert steps[1][1] == "favorita_store_n1d_xgboost"


@pytest.mark.unit
def test_resolve_pipeline_steps_arima_no_optimize() -> None:
    steps = resolve_pipeline_steps("favorita_arima")
    assert [s for s, _ in steps] == ["train", "predict"]


@pytest.mark.unit
def test_resolve_pipeline_steps_skip_optimize() -> None:
    steps = resolve_pipeline_steps("favorita_xgboost", skip_optimize=True)
    assert [s for s, _ in steps] == ["train", "predict"]


@pytest.mark.unit
def test_resolve_pipeline_steps_train_only() -> None:
    names = resolve_pipeline_config_names(
        "favorita_xgboost",
        skip_optimize=True,
        skip_predict=True,
    )
    assert names == ["favorita_store_n1d_xgboost"]


@pytest.mark.unit
def test_resolve_pipeline_steps_unknown_pipeline() -> None:
    with pytest.raises(ValueError, match="not found"):
        resolve_pipeline_steps("nonexistent_pipeline")
