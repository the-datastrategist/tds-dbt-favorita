"""Tests for model registry dispatch."""

import pytest

from vertex.models.registry import ensure_registered, get_runner


@pytest.mark.unit
class TestRegistry:
    def test_xgboost_runners_registered(self):
        ensure_registered()
        assert get_runner("xgboost", "train")
        assert get_runner("xgboost", "predict")
        assert get_runner("xgboost", "optimize")
        assert get_runner("xgboost_sklearn", "train")

    def test_random_forest_and_timeseries_registered(self):
        ensure_registered()
        assert get_runner("random_forest", "train")
        assert get_runner("arima", "predict")
        assert get_runner("sarima", "optimize")

    def test_unknown_runner_raises(self):
        ensure_registered()
        with pytest.raises(ValueError, match="No runner"):
            get_runner("prophet", "train")

    def test_train_config_has_runner(self):
        ensure_registered()
        runner = get_runner("xgboost", "train")
        assert runner.__name__ == "runner"
