"""Registry mapping (model_type, job step) to runner callables."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

Runner = Callable[[dict[str, Any]], Any]

_REGISTRY: dict[tuple[str, str], Runner] = {}


def register(model_type: str, step: str):
    """Decorator to register a config-driven runner."""

    def decorator(fn: Runner) -> Runner:
        _REGISTRY[(model_type, step)] = fn
        return fn

    return decorator


def register_alias(model_type: str, step: str, canonical_type: str) -> None:
    """Point model_type at the same runner as canonical_type."""
    key = (canonical_type, step)
    if key not in _REGISTRY:
        raise KeyError(f"No runner registered for {key}")
    _REGISTRY[(model_type, step)] = _REGISTRY[key]


def get_runner(model_type: str, step: str) -> Runner:
    ensure_registered()
    key = (model_type, step)
    if key not in _REGISTRY:
        registered = sorted(_REGISTRY.keys())
        raise ValueError(
            f"No runner for model_type={model_type!r}, step={step!r}. "
            f"Registered: {registered}"
        )
    return _REGISTRY[key]


def run_registered(config: dict[str, Any]) -> Any:
    """Dispatch a merged config dict to the appropriate runner."""
    from vertex.config.load_config import get_job_spec

    spec = get_job_spec(config)
    runner = get_runner(spec["model_type"], spec["step"])
    return runner(config)


def _lazy_runner(module_attr: tuple[str, str]) -> Runner:
    module_path, func_name = module_attr

    def runner(config: dict[str, Any]) -> Any:
        import importlib

        module = importlib.import_module(module_path)
        return getattr(module, func_name)(config)

    return runner


def _register_all() -> None:
    _REGISTRY[("xgboost", "train")] = _lazy_runner(
        ("vertex.models.xgboost.train_xgboost", "run_train_xgboost")
    )
    _REGISTRY[("xgboost", "predict")] = _lazy_runner(
        ("vertex.models.xgboost.predict_xgboost", "run_predict_xgboost")
    )
    _REGISTRY[("xgboost", "optimize")] = _lazy_runner(
        ("vertex.models.xgboost.optimize_xgboost", "run_optimize_xgboost")
    )
    register_alias("xgboost_sklearn", "train", "xgboost")
    register_alias("xgboost_sklearn", "predict", "xgboost")
    register_alias("xgboost_sklearn", "optimize", "xgboost")

    _REGISTRY[("random_forest", "train")] = _lazy_runner(
        ("vertex.models.sklearn.train_random_forest", "run_train_random_forest")
    )
    _REGISTRY[("random_forest", "predict")] = _lazy_runner(
        ("vertex.models.sklearn.predict_random_forest", "run_predict_random_forest")
    )
    _REGISTRY[("random_forest", "optimize")] = _lazy_runner(
        ("vertex.models.sklearn.optimize_random_forest", "run_optimize_random_forest")
    )

    for ts_type in ("arima", "sarima"):
        _REGISTRY[(ts_type, "train")] = _lazy_runner(
            ("vertex.models.timeseries.train_timeseries", "run_train_timeseries")
        )
        _REGISTRY[(ts_type, "predict")] = _lazy_runner(
            ("vertex.models.timeseries.predict_timeseries", "run_predict_timeseries")
        )
        _REGISTRY[(ts_type, "optimize")] = _lazy_runner(
            ("vertex.models.timeseries.optimize_timeseries", "run_optimize_timeseries")
        )


def ensure_registered() -> None:
    if not _REGISTRY:
        _register_all()
