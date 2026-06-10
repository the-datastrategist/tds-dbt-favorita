"""Tests for walk-forward backfill SQL and date iteration."""

from datetime import date

import pytest

from vertex.config.backfill import (
    BACKFILL_TRAIN_TEST_SIZE,
    apply_backfill_overrides,
    build_backfill_predict_sql,
    build_backfill_train_sql,
    iter_backfill_dates,
    parse_backfill_date,
    resolve_feature_table,
)
from vertex.config.load_config import load_model_config


@pytest.mark.unit
class TestBackfillDates:
    def test_parse_backfill_date(self):
        assert parse_backfill_date("2016-08-15") == date(2016, 8, 15)
        assert parse_backfill_date(date(2016, 8, 15)) == date(2016, 8, 15)

    def test_iter_backfill_dates_daily(self):
        assert list(
            iter_backfill_dates(date(2016, 8, 1), date(2016, 8, 3), interval_days=1)
        ) == [date(2016, 8, 1), date(2016, 8, 2), date(2016, 8, 3)]

    def test_iter_backfill_dates_weekly(self):
        assert list(
            iter_backfill_dates(date(2016, 8, 1), date(2016, 8, 15), interval_days=7)
        ) == [date(2016, 8, 1), date(2016, 8, 8), date(2016, 8, 15)]

    def test_iter_rejects_invalid_range(self):
        with pytest.raises(ValueError, match="start date"):
            list(iter_backfill_dates(date(2016, 8, 5), date(2016, 8, 1)))


@pytest.mark.unit
class TestBackfillSql:
    TABLE = "tds-favorita.favorita.int_sales_store_daily"
    AS_OF = date(2016, 8, 16)

    def test_train_sql_ends_day_before_as_of(self):
        sql = build_backfill_train_sql(self.TABLE, self.AS_OF, train_days=180)
        assert f"DATE '{self.AS_OF.isoformat()}'" in sql
        assert "INTERVAL 180 DAY" in sql
        assert "INTERVAL 1 DAY" in sql
        assert f"FROM `{self.TABLE}`" in sql

    def test_predict_sql_single_anchor_day(self):
        sql = build_backfill_predict_sql(self.TABLE, self.AS_OF)
        assert f"date = DATE '{self.AS_OF.isoformat()}'" in sql

    def test_resolve_feature_table_from_config(self):
        config = load_model_config("favorita_store_n1d_xgboost")
        assert resolve_feature_table(config) == self.TABLE

    def test_apply_backfill_overrides(self):
        config = load_model_config("favorita_store_n1d_xgboost")
        out = apply_backfill_overrides(
            config,
            as_of_date=self.AS_OF,
            train_days=90,
            feature_table=self.TABLE,
        )
        inputs = out["inputs"]
        assert inputs["backfill_as_of_date"] == "2016-08-16"
        assert inputs["test_size"] == BACKFILL_TRAIN_TEST_SIZE
        assert "model_run_id" not in inputs
        assert "DATE_SUB(DATE '2016-08-16', INTERVAL 1 DAY)" in inputs["train_sql_query"]
        assert "date = DATE '2016-08-16'" in inputs["predict_sql_query"]
