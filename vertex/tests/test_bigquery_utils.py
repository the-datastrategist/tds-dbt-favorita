"""Tests for BigQuery load helpers."""

import json

import pandas as pd
import pytest

from vertex.utils.bigquery_utils import (
    _coerce_value_for_bq_type,
    _json_safe,
    _prepare_row_for_insert,
    validate_bq_identifier,
    validate_bq_table_id,
    vertex_safe_run_id,
)


@pytest.mark.unit
class TestBigQueryUtils:
    def test_vertex_safe_run_id_replaces_underscores(self):
        assert vertex_safe_run_id("favorita_xgboost_train", "7c4c022f") == (
            "favorita-xgboost-train-7c4c022f"
        )

    def test_coerce_json_from_string(self):
        payload = {"mae": 1.5}
        encoded = json.dumps(payload)
        assert json.loads(_coerce_value_for_bq_type(encoded, "JSON")) == payload

    def test_json_safe_replaces_nan_and_infinity(self):
        payload = {
            "missing": float("nan"),
            "monotone_constraints": float("inf"),
            "n_estimators": 100,
        }
        assert _json_safe(payload) == {
            "missing": None,
            "monotone_constraints": None,
            "n_estimators": 100,
        }

    def test_coerce_json_strips_nan_from_sklearn_params_string(self):
        encoded = json.dumps({"missing": float("nan"), "max_depth": 6})
        assert json.loads(_coerce_value_for_bq_type(encoded, "JSON")) == {
            "missing": None,
            "max_depth": 6,
        }

    def test_prepare_row_maps_json_columns(self):
        schema = {"parameters": "JSON", "run_at": "TIMESTAMP", "config_name": "STRING"}
        row = {
            "parameters": json.dumps({"n_estimators": 100}),
            "run_at": pd.Timestamp("2024-01-01 12:00:00"),
            "config_name": "favorita_xgboost_train",
            "unknown_col": "drop-me",
        }
        prepared = _prepare_row_for_insert(row, schema)
        assert json.loads(prepared["parameters"]) == {"n_estimators": 100}
        assert prepared["config_name"] == "favorita_xgboost_train"
        assert "unknown_col" not in prepared

    def test_validate_bq_table_id_accepts_two_and_three_part_refs(self):
        assert validate_bq_table_id("favorita.int_sales_daily") == "favorita.int_sales_daily"
        assert (
            validate_bq_table_id("my-project.favorita.int_sales_daily")
            == "my-project.favorita.int_sales_daily"
        )

    @pytest.mark.parametrize(
        "table_id",
        [
            "",
            "only_one_part",
            "a.b.c.d",
            "dataset.table; DROP TABLE x",
            "proj.data set.table",
        ],
    )
    def test_validate_bq_table_id_rejects_unsafe_values(self, table_id: str):
        with pytest.raises(ValueError, match="Invalid BigQuery"):
            validate_bq_table_id(table_id)

    def test_validate_bq_identifier_rejects_injection(self):
        with pytest.raises(ValueError, match="Invalid BigQuery"):
            validate_bq_identifier("col; DROP", label="column")
