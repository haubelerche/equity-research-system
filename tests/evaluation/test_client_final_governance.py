from __future__ import annotations

from backend.dataset.dqf import score_materiality
from backend.evaluation.governance import (
    decomposition_issues,
    forecast_sanity_issues,
    is_valid_bridge,
    valuation_reproduction_issues,
)
from backend.valuation_method_policy import select_valuation_methods


def _line(value: float) -> dict:
    return {
        "forecast": {"2026F": value},
        "drivers": ["approved_driver"],
        "evidence_refs": ["fact:1"],
        "status": "observed",
    }


def test_aggregate_only_forecast_is_not_client_final_decomposition() -> None:
    revenue = {
        "by_channel": {"all_channels": {**_line(100), "status": "aggregate_only"}},
        "by_product_group": {"all_products": {**_line(100), "status": "aggregate_only"}},
    }
    assert set(decomposition_issues(revenue)) >= {
        "pharma_driver_channels_insufficient",
        "pharma_driver_product_groups_missing",
    }


def test_real_decomposition_reconciles_to_aggregate() -> None:
    revenue = {
        "by_channel": {"ETC": _line(60), "OTC": _line(40)},
        "by_product_group": {"core": _line(100)},
        "company_growth": {"2026F": 100},
    }
    assert decomposition_issues(revenue) == []


def test_bridge_requires_reconciled_deltas_and_evidence() -> None:
    bridge = {
        "from_period": "2025A",
        "to_period": "2026F",
        "line_items": [
            {"delta": 10, "reason": "Mix", "evidence_refs": ["fact:mix"]},
            {"delta": -2, "reason": "FX", "evidence_refs": ["fact:fx"]},
        ],
        "total_delta": 8,
    }
    assert is_valid_bridge(bridge)
    bridge["total_delta"] = 9
    assert not is_valid_bridge(bridge)


def test_sga_decline_and_net_margin_jump_require_bridge() -> None:
    issues = forecast_sanity_issues({
        "forecast_years": [
            {"label": "2025A", "revenue": 100, "sga": -20, "net_margin": 0.10},
            {"label": "2026F", "revenue": 110, "sga": -15, "net_margin": 0.15},
        ]
    })
    assert "sga_decline_requires_bridge:2026F" in issues
    assert "net_margin_jump_requires_bridge:2026F" in issues


def test_weighted_target_price_must_be_reproducible() -> None:
    valuation = {
        "selected_methods": ["FCFF", "FCFE"],
        "method_weights": {"FCFF": 60, "FCFE": 40},
        "fcff": {"target_price_vnd": 100},
        "fcfe": {"target_price_vnd": 80},
        "weighted_target_price": {"raw": 99},
    }
    assert "weighted_target_price_not_reproducible" in valuation_reproduction_issues(valuation)


def test_materiality_uses_financial_impact_dimensions() -> None:
    score = score_materiality({"event_type": "management_change", "revenue_impact_pct": 12})
    assert score["level"] == "high"
    assert score["dimensions"]["revenue"] == 12


def test_valuation_policy_explains_selected_and_excluded_methods() -> None:
    policy = select_valuation_methods(
        fcff={"target_price_vnd": 100},
        fcfe={"target_price_vnd": 90},
        dividend_history_available=False,
    )
    assert policy["selected_methods"] == ["FCFF", "FCFE"]
    assert policy["method_weights"] == {"FCFF": 60.0, "FCFE": 40.0}
    assert any(item["method"] == "DDM" for item in policy["excluded_methods"])
