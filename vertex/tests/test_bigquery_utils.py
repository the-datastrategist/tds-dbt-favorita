"""Tests for BigQuery load helpers."""

import json
from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from vertex.utils.bigquery_utils import (
    INSERT_ROWS_BATCH_SIZE,
    _bq_param,
    _coerce_value_for_bq_type,
    _json_safe,
    _prepare_row_for_insert,
    insert_rows_idempotent,
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

    def test_prepare_row_promotes_date_to_timestamp(self):
        prepared = _prepare_row_for_insert(
            {"data_cutoff": date(2024, 1, 2)}, {"data_cutoff": "TIMESTAMP"}
        )

        assert prepared["data_cutoff"] == "2024-01-02 00:00:00"

    def test_prepare_row_maps_nan_string_value_to_null(self):
        prepared = _prepare_row_for_insert(
            {"fallback_reason": float("nan")}, {"fallback_reason": "STRING"}
        )

        assert prepared["fallback_reason"] is None

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("2016-08-08", "2016-08-08 00:00:00"),
            ("2016-08-08T12:34:56", "2016-08-08 12:34:56"),
            ("2016-08-08T12:34:56-04:00", "2016-08-08 16:34:56"),
        ],
    )
    def test_coerce_timestamp_strings(self, value: str, expected: str):
        assert _coerce_value_for_bq_type(value, "TIMESTAMP") == expected

    def test_query_parameter_honors_date_schema(self):
        value = pd.Timestamp("2024-01-02")

        parameter = _bq_param("origin_start", value, bq_type="DATE")

        assert parameter.type_ == "DATE"
        assert parameter.value.isoformat() == "2024-01-02"

    def test_query_parameter_promotes_date_to_timestamp(self):
        parameter = _bq_param("data_cutoff", date(2024, 1, 2), bq_type="TIMESTAMP")

        assert parameter.type_ == "TIMESTAMP"
        assert parameter.value == datetime(2024, 1, 2)

    def test_query_parameter_honors_repeated_string_schema(self):
        parameter = _bq_param("dimensions", ["store_id", "product_id"], bq_type="ARRAY<STRING>")

        assert parameter.array_type == "STRING"
        assert parameter.values == ["store_id", "product_id"]

    def test_query_parameter_honors_json_schema(self):
        parameter = _bq_param("contract_json", {"horizons": [7]}, bq_type="JSON")

        assert parameter.type_ == "JSON"
        assert json.loads(parameter.value) == {"horizons": [7]}

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

    @patch("vertex.utils.bigquery_utils.bigquery.Client")
    def test_idempotent_insert_batches_rows_through_staging_table(self, client_cls):
        rows = [{"prediction_id": "p-1", "prediction": 10.0}]
        client = MagicMock()
        client_cls.return_value = client
        destination = MagicMock()
        prediction_id_field = MagicMock()
        prediction_id_field.name = "prediction_id"
        prediction_id_field.field_type = "STRING"
        prediction_field = MagicMock()
        prediction_field.name = "prediction"
        prediction_field.field_type = "FLOAT64"
        destination.schema = [prediction_id_field, prediction_field]
        destination.reference.project = "proj"
        destination.reference.dataset_id = "ds"
        destination.reference.table_id = "predictions"
        client.get_table.return_value = destination
        client.insert_rows_json.return_value = []
        client.query.return_value.num_dml_affected_rows = 1

        inserted = insert_rows_idempotent(
            rows, "proj.ds.predictions", id_column="prediction_id", project_id="proj"
        )

        assert inserted == 1
        client.create_table.assert_called_once()
        client.insert_rows_json.assert_called_once()
        merge_sql = client.query.call_args.args[0]
        assert "MERGE `proj.ds.predictions`" in merge_sql
        assert "ON T.prediction_id = S.prediction_id" in merge_sql
        assert "WHEN MATCHED" not in merge_sql
        client.delete_table.assert_called_once_with(
            client.create_table.call_args.args[0], not_found_ok=True
        )

    def test_idempotent_insert_rejects_duplicate_ids(self):
        rows = [{"metric_id": "m-1"}, {"metric_id": "m-1"}]

        with pytest.raises(ValueError, match="Duplicate 'metric_id'"):
            insert_rows_idempotent(rows, "proj.ds.metrics", id_column="metric_id")
