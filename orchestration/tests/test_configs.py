"""Unit tests for Prefect config helpers."""

from __future__ import annotations

import pytest

from orchestration.utils.configs import list_train_config_names, resolve_train_config_names


@pytest.mark.unit
def test_list_train_config_names_excludes_legacy_alias() -> None:
    names = list_train_config_names()
    assert names == ["favorita_xgboost_train"]
    assert "train_xgboost" not in names


@pytest.mark.unit
def test_list_train_config_names_include_legacy() -> None:
    names = list_train_config_names(include_legacy_aliases=True)
    assert names == ["favorita_xgboost_train"]
    assert "train_xgboost" not in names


@pytest.mark.unit
def test_resolve_train_config_names_single() -> None:
    assert resolve_train_config_names("favorita_arima_train") == ["favorita_arima_train"]


@pytest.mark.unit
def test_resolve_train_config_names_all() -> None:
    names = resolve_train_config_names(None, train_all=True)
    assert names == ["favorita_xgboost_train"]


@pytest.mark.unit
def test_resolve_train_config_names_conflict() -> None:
    with pytest.raises(ValueError, match="not both"):
        resolve_train_config_names("favorita_xgboost_train", train_all=True)


@pytest.mark.unit
def test_resolve_train_config_names_requires_input() -> None:
    with pytest.raises(ValueError, match="config_name"):
        resolve_train_config_names(None, train_all=False)
