"""Tests for BigQuery load helpers."""

import json
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from vertex.utils.bigquery_utils import (
    INSERT_ROWS_BATCH_SIZE,
    _coerce_value_for_bq_type,
    _json_safe,
    _prepare_row_for_insert,
    load_to_bigquery,
    validate_bq_identifier,
    validate_bq_table_id,
    vertex_safe_run_id,
)


@pytest.mark.unit
class TestBigQueryUtils:
    def test_vertex_safe_run_id_replaces_underscores(self):
        assert vertex_safe_run_id("favorita_store_n1d_xgboost", "7c4c022f") == (
            "favorita-store-n1d-xgboost-7c4c022f"
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
            "config_name": "favorita_store_n1d_xgboost",
            "unknown_col": "drop-me",
        }
        prepared = _prepare_row_for_insert(row, schema)
        assert json.loads(prepared["parameters"]) == {"n_estimators": 100}
        assert prepared["config_name"] == "favorita_store_n1d_xgboost"
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

    @patch("vertex.utils.bigquery_utils.bigquery.Client")
    def test_load_to_bigquery_batches_large_inserts(self, mock_client_cls):
        row_count = INSERT_ROWS_BATCH_SIZE + 50
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_table = MagicMock()
        mock_table.schema = [MagicMock(name="config_name", field_type="STRING")]
        mock_client.get_table.return_value = mock_table
        mock_client.insert_rows_json.return_value = []

        rows = [{"config_name": f"row-{index}"} for index in range(row_count)]
        load_to_bigquery(rows, "proj.ds.table", project_id="proj")

        assert mock_client.insert_rows_json.call_count == 2
        first_batch, second_batch = mock_client.insert_rows_json.call_args_list
        assert len(first_batch.args[1]) == INSERT_ROWS_BATCH_SIZE
        assert len(second_batch.args[1]) == 50
