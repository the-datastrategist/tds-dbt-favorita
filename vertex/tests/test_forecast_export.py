"""Tests for the stable batch-export boundary."""

from unittest.mock import MagicMock, patch

import pytest

from scripts.export_forecast import export_forecast

RUN_ID = "a" * 64


@pytest.mark.unit
@patch("scripts.export_forecast.bigquery.Client")
def test_parquet_export_uses_parameterized_run_id(client_class):
    client = MagicMock()
    client_class.return_value = client
    result = export_forecast(
        project_id="tds-favorita",
        source_view="tds-favorita.favorita.published_forecasts_by_run",
        forecast_run_id=RUN_ID,
        destination="gs://favorita-exports/run/*.parquet",
        format="parquet",
    )
    query = client.query.call_args.args[0]
    config = client.query.call_args.kwargs["job_config"]
    assert "format='PARQUET'" in query
    assert "@forecast_run_id" in query
    assert config.query_parameters[0].value == RUN_ID
    assert result["format"] == "PARQUET"


@pytest.mark.unit
@pytest.mark.parametrize(
    "destination", ["https://example.com/file", "gs://bucket/no-wildcard", "gs://b/x'; DROP *"]
)
def test_export_rejects_unsafe_destinations(destination):
    with pytest.raises(ValueError, match="gs://"):
        export_forecast(
            project_id="tds-favorita",
            source_view="tds-favorita.favorita.published_forecasts_by_run",
            forecast_run_id=RUN_ID,
            destination=destination,
            format="csv",
        )
