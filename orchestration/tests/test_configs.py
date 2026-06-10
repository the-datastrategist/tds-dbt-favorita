"""Unit tests for Prefect config helpers."""

from __future__ import annotations

import pytest

from orchestration.utils.configs import list_train_config_names, resolve_train_config_names


@pytest.mark.unit
def test_list_train_config_names() -> None:
    names = list_train_config_names()
    assert names == ["favorita_store_n1d_xgboost"]


@pytest.mark.unit
def test_resolve_train_config_names_single() -> None:
    assert resolve_train_config_names("favorita_store_n1d_arima") == ["favorita_store_n1d_arima"]


@pytest.mark.unit
def test_resolve_train_config_names_all() -> None:
    names = resolve_train_config_names(None, train_all=True)
    assert names == ["favorita_store_n1d_xgboost"]


@pytest.mark.unit
def test_resolve_train_config_names_conflict() -> None:
    with pytest.raises(ValueError, match="not both"):
        resolve_train_config_names("favorita_store_n1d_xgboost", train_all=True)


@pytest.mark.unit
def test_resolve_train_config_names_requires_input() -> None:
    with pytest.raises(ValueError, match="config_name"):
        resolve_train_config_names(None, train_all=False)
