"""Tests for the ordered scheduled forecast publication stages."""

from datetime import datetime, timezone

import pandas as pd
import pytest

from vertex.config.forecast_contract import load_forecast_contract
from vertex.config.hierarchy import load_hierarchy_config
from vertex.evaluation.forecast_pipeline import (
    ForecastRunPins,
    build_forecast_run_id,
    eligibility_snapshot_id,
    execute_forecast_pipeline,
)
from vertex.evaluation.reconciliation import expand_leaf_predictions

ORIGIN = pd.Timestamp("2026-07-18")


def _predictions() -> pd.DataFrame:
    run_at = datetime(2026, 7, 18, 9, tzinfo=timezone.utc)
    return pd.DataFrame(
        [
            {
                "prediction_id": f"prediction-{store_id}",
                "predict_run_id": "source-run",
                "model_run_id": "model-run-1",
                "model_id": "model-1",
                "config_name": "favorita_store_h7_xgboost",
                "model_family": "tree",
                "model_type": "xgboost",
                "run_at": run_at,
                "date": ORIGIN,
                "forecast_date": ORIGIN + pd.Timedelta(days=7),
                "forecast_horizon": 7,
                "store_id": store_id,
                "prediction": 10.0 + store_id,
                "model_artifact_uri": "gs://models/run/model.json",
            }
            for store_id in (1, 2)
        ]
    )


def _calibration() -> pd.DataFrame:
    rows = []
    for store_id in (1, 2):
        entity = f'{{"store_id":{store_id}}}'
        for index in range(30):
            prediction = 10.0 + store_id
            rows.append(
                {
                    "entity_key_json": entity,
                    "horizon": 7,
                    "actual": prediction + (-1.0 if index % 2 else 1.0),
                    "prediction": prediction,
                }
            )
    return pd.DataFrame(rows)


def _pins(predictions: pd.DataFrame) -> ForecastRunPins:
    contract = load_forecast_contract("vertex/config/forecast_contract_publication.yaml")
    return ForecastRunPins(
        champion_candidate_id="candidate-1",
        model_run_id="model-run-1",
        feature_version="features-1",
        feature_availability_hash="availability-1",
        data_cutoff=ORIGIN,
        source_cutoff_json={"sales": "2026-07-18"},
        eligibility_snapshot_id=eligibility_snapshot_id(predictions, contract),
        code_sha="abc123",
    )


@pytest.mark.unit
def test_pipeline_is_deterministic_and_produces_validated_draft() -> None:
    contract = load_forecast_contract("vertex/config/forecast_contract_publication.yaml")
    predictions = _predictions()
    pins = _pins(predictions)
    completed = datetime(2026, 7, 18, 10, tzinfo=timezone.utc)

    first = execute_forecast_pipeline(
        predictions,
        _calibration(),
        contract=contract,
        pins=pins,
        completed_at=completed,
    )
    retry = execute_forecast_pipeline(
        predictions,
        _calibration(),
        contract=contract,
        pins=pins,
        completed_at=completed,
    )

    assert first.forecast_run_id == retry.forecast_run_id
    assert first.rows["forecast_output_id"].tolist() == retry.rows["forecast_output_id"].tolist()
    assert [stage["stage_name"] for stage in first.stage_records] == [
        "score",
        "route",
        "calibrate",
        "reconcile",
        "validate",
    ]
    assert first.rows["forecast_status"].eq("draft").all()
    assert first.rows["forecast_strategy"].eq("global_model").all()
    assert first.rows["calibration_run_id"].notna().all()
    assert first.rows["reconciliation_method"].eq("none").all()
    assert all(check["passed"] for check in first.validation_checks)


@pytest.mark.unit
def test_feature_availability_hash_is_a_material_run_pin() -> None:
    contract = load_forecast_contract("vertex/config/forecast_contract_publication.yaml")
    predictions = _predictions()
    pins = _pins(predictions)
    changed_registry = ForecastRunPins(
        **{
            **pins.__dict__,
            "feature_availability_hash": "availability-2",
        }
    )

    assert build_forecast_run_id(
        contract, forecast_origin=ORIGIN, pins=pins
    ) != build_forecast_run_id(contract, forecast_origin=ORIGIN, pins=changed_registry)


@pytest.mark.unit
def test_pipeline_rejects_changed_eligibility_after_pinning() -> None:
    contract = load_forecast_contract("vertex/config/forecast_contract_publication.yaml")
    predictions = _predictions()
    pins = _pins(predictions)
    changed = predictions.iloc[:1].copy()

    with pytest.raises(ValueError, match="pinned eligibility snapshot"):
        execute_forecast_pipeline(changed, _calibration(), contract=contract, pins=pins)


@pytest.mark.unit
def test_pipeline_blocks_data_cutoff_after_origin() -> None:
    contract = load_forecast_contract("vertex/config/forecast_contract_publication.yaml")
    predictions = _predictions()
    pins = ForecastRunPins(
        **{
            **_pins(predictions).__dict__,
            "data_cutoff": ORIGIN + pd.Timedelta(days=1),
        }
    )

    with pytest.raises(ValueError, match="point_in_time_cutoff"):
        execute_forecast_pipeline(predictions, _calibration(), contract=contract, pins=pins)


@pytest.mark.unit
def test_pipeline_publishes_coherent_company_and_store_nodes() -> None:
    contract = load_forecast_contract(
        "vertex/config/forecast_contract_hierarchical_publication.yaml"
    )
    hierarchy = load_hierarchy_config("vertex/config/hierarchy.yaml")
    nodes = pd.DataFrame(
        [
            {"node_id": "company:all", "level_name": "company", "node_key_json": "{}"},
            {"node_id": "store:1", "level_name": "store", "node_key_json": '{"store_id":1}'},
            {"node_id": "store:2", "level_name": "store", "node_key_json": '{"store_id":2}'},
        ]
    )
    edges = pd.DataFrame(
        [
            {"parent_node_id": "company:all", "child_node_id": "store:1"},
            {"parent_node_id": "company:all", "child_node_id": "store:2"},
        ]
    )
    predictions = expand_leaf_predictions(_predictions(), nodes, edges, leaf_keys=("store_id",))
    pins = ForecastRunPins(
        **{
            **_pins(_predictions()).__dict__,
            "eligibility_snapshot_id": eligibility_snapshot_id(predictions, contract),
        }
    )

    result = execute_forecast_pipeline(
        predictions,
        _calibration(),
        contract=contract,
        pins=pins,
        hierarchy_config=hierarchy,
        hierarchy_nodes=nodes,
        hierarchy_edges=edges,
    )

    assert len(result.rows) == 3
    assert result.rows["hierarchy_version"].eq("v1").all()
    assert result.rows["reconciliation_method"].eq("bottom_up").all()
    values = dict(zip(predictions["node_id"], result.rows["prediction_p50"]))
    assert values["company:all"] == values["store:1"] + values["store:2"]
