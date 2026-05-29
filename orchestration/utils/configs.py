"""Helpers for model_config.yaml train job discovery."""

from __future__ import annotations

from pathlib import Path

from vertex.config.load_config import list_run_config_names


def list_train_config_names(
    config_path: str | Path | None = None,
    *,
    include_legacy_aliases: bool = False,
) -> list[str]:
    """
    Return sorted train config names with include_in_run: true.

    By default excludes legacy aliases such as train_xgboost (use favorita_xgboost_train).
    """
    return list_run_config_names(
        config_path,
        step="train",
        include_legacy_aliases=include_legacy_aliases,
    )


def resolve_train_config_names(
    config_name: str | None,
    *,
    train_all: bool = False,
    config_path: str | Path | None = None,
    include_legacy_aliases: bool = False,
) -> list[str]:
    """Resolve which train configs to run from flow parameters."""
    if train_all:
        if config_name:
            raise ValueError("Set either config_name or train_all=true, not both.")
        return list_train_config_names(
            config_path,
            include_legacy_aliases=include_legacy_aliases,
        )

    if config_name:
        return [config_name]

    raise ValueError(
        "Provide config_name (e.g. favorita_xgboost_train) or set train_all=true "
        "to run configs with include_in_run: true."
    )
