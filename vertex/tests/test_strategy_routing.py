"""Tests for series classification and cold-start routing."""

import pandas as pd
import pytest

from vertex.evaluation.strategy_routing import (
    RoutingPolicy,
    StrategyAvailability,
    attach_strategy_metadata,
    build_classification_rows,
    choose_forecast_strategy,
    classify_series,
    route_from_contract,
)


@pytest.mark.unit
def test_classifier_distinguishes_cold_intermittent_and_sufficient_series():
    observations = pd.DataFrame(
        {
            "entity": ["cold"] * 4 + ["intermittent"] * 30 + ["regular"] * 30,
            "demand": [0, 1, 0, 0]
            + [5 if index in {0, 10, 20} else 0 for index in range(30)]
            + [5] * 30,
        }
    )
    profiles = classify_series(
        observations,
        entity_columns=["entity"],
        demand_column="demand",
        policy=RoutingPolicy(minimum_history=10, minimum_nonzero_observations=2),
    ).set_index("entity_key_json")

    cold = profiles.loc['{"entity":"cold"}']
    intermittent = profiles.loc['{"entity":"intermittent"}']
    regular = profiles.loc['{"entity":"regular"}']
    assert bool(cold["is_cold_start"])
    assert intermittent["recommended_strategy"] == "intermittent_rate_baseline"
    assert intermittent["average_demand_interval"] == 10.0
    assert regular["recommended_strategy"] == "entity_model"
    assert not bool(regular["is_intermittent"])
    assert profiles["classification_run_id"].notna().all()


@pytest.mark.unit
def test_router_uses_ordered_fallbacks_and_never_returns_missing_strategy():
    global_decision = choose_forecast_strategy(is_cold_start=True, is_intermittent=False)
    assert global_decision.forecast_strategy == "global_model"
    assert global_decision.fallback_reason == "cold_start"

    baseline_decision = choose_forecast_strategy(
        is_cold_start=False,
        is_intermittent=True,
        availability=StrategyAvailability(
            entity_model=False,
            global_model=False,
            aggregate_allocation=False,
        ),
    )
    assert baseline_decision.forecast_strategy == "intermittent_rate_baseline"
    assert baseline_decision.confidence_flag == "low"
    enriched = attach_strategy_metadata(
        pd.DataFrame({"prediction": [1.0]}), decision=baseline_decision
    )
    assert enriched["forecast_strategy"].notna().all()


@pytest.mark.unit
def test_router_fails_when_policy_has_no_available_strategy():
    with pytest.raises(ValueError, match="no available forecast strategy"):
        choose_forecast_strategy(
            is_cold_start=True,
            is_intermittent=False,
            availability=StrategyAvailability(False, False, False, False, False),
        )


@pytest.mark.unit
def test_classification_rows_have_retry_stable_policy_lineage():
    profiles = classify_series(
        pd.DataFrame({"store_id": [1] * 30, "demand": [1.0] * 30}),
        entity_columns=["store_id"],
        demand_column="demand",
    )
    policy = RoutingPolicy()
    first = build_classification_rows(
        profiles,
        forecast_contract_name="daily",
        forecast_contract_hash="contract",
        forecast_origin="2026-07-24",
        policy=policy,
    )
    second = build_classification_rows(
        profiles,
        forecast_contract_name="daily",
        forecast_contract_hash="contract",
        forecast_origin="2026-07-24",
        policy=policy,
    )
    assert first["classification_id"].tolist() == second["classification_id"].tolist()
    assert first.loc[0, "routing_policy_hash"] == policy.hash


@pytest.mark.unit
def test_contract_routing_covers_cold_intermittent_and_default():
    routing = {
        "allowed_strategies": [
            "entity_model",
            "global_model",
            "intermittent_rate_baseline",
            "business_default",
        ],
        "fallback_order": {
            "cold_start": ["global_model", "business_default"],
            "intermittent": ["intermittent_rate_baseline", "business_default"],
        },
        "business_default": 0.0,
    }
    cold = route_from_contract(
        is_cold_start=True,
        is_intermittent=False,
        routing=routing,
        available_strategies={"global_model"},
    )
    intermittent = route_from_contract(
        is_cold_start=False,
        is_intermittent=True,
        routing=routing,
        available_strategies={"intermittent_rate_baseline"},
    )
    default = route_from_contract(
        is_cold_start=False,
        is_intermittent=False,
        routing=routing,
        available_strategies=set(),
    )
    assert cold.forecast_strategy == "global_model"
    assert intermittent.forecast_strategy == "intermittent_rate_baseline"
    assert default.forecast_strategy == "business_default"
