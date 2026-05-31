"""Tests for config-driven data loading."""

import pytest

from vertex.utils.data_loading import (
    PREDICT_SQL_QUERY_KEY,
    TRAIN_SQL_QUERY_KEY,
    has_step_data_source,
    load_data_from_config,
    resolve_input_sql,
    resolve_training_sql,
)


def _config(*, step: str, inputs: dict) -> dict:
    return {"name": "demo", "job": {"step": step}, "inputs": inputs}


@pytest.mark.unit
class TestResolveInputSql:
    def test_resolves_train_sql_query(self):
        config = _config(
            step="train",
            inputs={
                TRAIN_SQL_QUERY_KEY: "SELECT * FROM `proj.ds.train_table`",
                PREDICT_SQL_QUERY_KEY: "SELECT * FROM `proj.ds.predict_table`",
            },
        )
        assert resolve_input_sql(config) == "SELECT * FROM `proj.ds.train_table`"

    def test_resolves_predict_sql_query(self):
        config = _config(
            step="predict",
            inputs={
                TRAIN_SQL_QUERY_KEY: "SELECT * FROM `proj.ds.train_table`",
                PREDICT_SQL_QUERY_KEY: "SELECT * FROM `proj.ds.predict_table`",
            },
        )
        assert resolve_input_sql(config) == "SELECT * FROM `proj.ds.predict_table`"

    def test_optimize_uses_train_sql_query(self):
        config = _config(
            step="optimize",
            inputs={
                TRAIN_SQL_QUERY_KEY: "SELECT * FROM `proj.ds.train_table`",
            },
        )
        assert resolve_input_sql(config) == "SELECT * FROM `proj.ds.train_table`"

    def test_resolve_training_sql_uses_train_query_not_predict(self):
        config = _config(
            step="predict",
            inputs={
                TRAIN_SQL_QUERY_KEY: "SELECT * FROM `proj.ds.train_table`",
                PREDICT_SQL_QUERY_KEY: "SELECT * FROM `proj.ds.predict_table`",
            },
        )
        assert resolve_training_sql(config) == "SELECT * FROM `proj.ds.train_table`"

    def test_legacy_source_table(self):
        config = {"inputs": {"source_table": "proj.ds.legacy_table"}}
        assert resolve_input_sql(config) == "SELECT * FROM `proj.ds.legacy_table`"

    def test_missing_train_sql_query_raises(self):
        config = _config(
            step="train",
            inputs={
                PREDICT_SQL_QUERY_KEY: "SELECT * FROM `proj.ds.predict_table`",
            },
        )
        with pytest.raises(ValueError, match="train_sql_query"):
            resolve_input_sql(config)

    def test_missing_predict_sql_query_raises(self):
        config = _config(
            step="predict",
            inputs={
                TRAIN_SQL_QUERY_KEY: "SELECT * FROM `proj.ds.train_table`",
            },
        )
        with pytest.raises(ValueError, match="predict_sql_query"):
            resolve_input_sql(config)

    def test_missing_step_raises(self):
        config = {
            "inputs": {
                TRAIN_SQL_QUERY_KEY: "SELECT * FROM `proj.ds.train_table`",
            }
        }
        with pytest.raises(ValueError, match="job.step"):
            resolve_input_sql(config)


@pytest.mark.unit
class TestHasStepDataSource:
    def test_step_specific_sql_queries(self):
        inputs = {
            TRAIN_SQL_QUERY_KEY: "SELECT 1",
        }
        assert has_step_data_source(inputs, "train") is True
        assert has_step_data_source(inputs, "optimize") is True
        assert has_step_data_source(inputs, "predict") is False

    def test_legacy_source_table_covers_all_steps(self):
        inputs = {"source_table": "proj.ds.table"}
        assert has_step_data_source(inputs, "train") is True
        assert has_step_data_source(inputs, "predict") is True


@pytest.mark.unit
class TestLoadDataFromConfig:
    def test_rejects_unsafe_source_table(self):
        config = {"inputs": {"source_table": "dataset.table; DROP TABLE secrets"}}
        with pytest.raises(ValueError, match="Invalid BigQuery"):
            load_data_from_config(config)
