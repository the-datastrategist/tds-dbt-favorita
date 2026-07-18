"""Tests for gated, idempotent forecast publication."""

from datetime import datetime, timezone

import pandas as pd
import pytest

from vertex.config.forecast_contract import validate_forecast_contract
from vertex.utils.forecast_publication import build_publication_records, validate_publication_batch


def _contract(*, reconciliation_policy: str = "none"):
    return validate_forecast_contract(
        {
            "forecast": {
                "name": "store_daily",
                "target": "demand_units",
                "target_unit": "units",
                "dimensions": ["store_id"],
                "frequency": "day",
                "timezone": "UTC",
                "issue_schedule": "0 6 * * *",
                "horizons": [1, 7],
                "quantiles": [0.1, 0.5, 0.9],
                "training_window_days": 180,
                "known_future_features": ["promotion"],
                "observed_features": ["sales"],
                "hierarchy": [] if reconciliation_policy == "none" else ["company", "store"],
                "reconciliation_policy": reconciliation_policy,
                "demand_policy": "observed_sales_only",
            }
        }
    )


def _rows(contract) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "forecast_output_id": f"output-{horizon}",
                "forecast_run_id": "run-1",
                "forecast_contract_hash": contract.hash,
                "entity_key_json": '{"store_id":1}',
                "target_date": f"2026-07-{18 + horizon:02d}",
                "horizon": horizon,
                "prediction_p10": 8.0,
                "prediction_p50": 10.0,
                "prediction_p90": 12.0,
                "forecast_strategy": "entity_model",
                "confidence_flag": "high",
                "calibration_method": "symmetric_split_conformal",
                "calibration_run_id": "calibration-1",
                "hierarchy_version": None,
                "reconciliation_method": "none",
                "reconciliation_run_id": None,
                "feature_version": "features-1",
                "code_sha": "abc123",
                "data_cutoff": "2026-07-18T00:00:00Z",
            }
            for horizon in (1, 7)
        ]
    )


@pytest.mark.unit
def test_complete_calibrated_batch_passes_publication_gates():
    contract = _contract()
    validate_publication_batch(_rows(contract), contract)


@pytest.mark.unit
def test_incomplete_horizons_block_publication():
    contract = _contract()
    with pytest.raises(ValueError, match="incomplete horizons"):
        validate_publication_batch(_rows(contract).iloc[:1], contract)


@pytest.mark.unit
def test_unordered_quantiles_block_publication():
    contract = _contract()
    rows = _rows(contract)
    rows.loc[0, "prediction_p10"] = 11.0
    with pytest.raises(ValueError, match="P10 <= P50 <= P90"):
        validate_publication_batch(rows, contract)


@pytest.mark.unit
def test_hierarchy_requires_reconciliation_lineage():
    contract = _contract(reconciliation_policy="bottom_up")
    rows = _rows(contract)
    rows["forecast_contract_hash"] = contract.hash
    rows["reconciliation_method"] = "bottom_up"
    with pytest.raises(ValueError, match="requires reconciliation lineage"):
        validate_publication_batch(rows, contract)


@pytest.mark.unit
def test_publication_records_are_idempotent_and_use_calibrated_median():
    contract = _contract()
    rows = _rows(contract)
    timestamp = datetime(2026, 7, 18, tzinfo=timezone.utc)
    first = build_publication_records(
        rows,
        idempotency_key="daily-2026-07-18",
        actor="scheduler",
        destination="canonical_bigquery",
        published_at=timestamp,
    )
    retry = build_publication_records(
        rows,
        idempotency_key="daily-2026-07-18",
        actor="scheduler",
        destination="canonical_bigquery",
        published_at=timestamp,
    )

    assert first == retry
    approvals, publications = first
    assert approvals[0]["approved_value"] == 10.0
    assert publications[0]["published_value"] == 10.0
    assert publications[0]["approval_id"] == approvals[0]["approval_id"]
