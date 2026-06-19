"""Group B — renderer keeps raw valuation policy as metadata only.

The report view model must keep raw computed target evidence visible while the
headline target is clamped to the market sanity band.
"""
from __future__ import annotations

import pytest

from backend.reporting import client_report_view_model as vm
from backend.valuation_method_policy import build_valuation_publishability_policy


def _dbd_like_artifact() -> dict:
    # FCFF 27,207 (low conf), FCFE blocked, P/E 49,336, core P/E+cash 63,246,
    # price ~50,200 → critical divergence; nothing publishable.
    return {
        "current_price_vnd": 50_200.0,
        "fcff": {"target_price_vnd": 27_207.0},
        "fcfe": {"target_price_vnd": None, "fcfe_table": [{"fcfe": None, "net_borrowing": None}]},
        "blend_dcf": {
            "price_fcff_vnd": 27_207.0, "price_fcfe_vnd": None,
            "target_price_dcf_vnd": 27_207.0, "is_draft_only": True,
        },
        "pe_forward": {"target_price_vnd": 49_336.0},
        "core_pe_net_cash": {"target_price_vnd": 63_246.0},
        "sensitivity": {"fcff_wacc_g": {}, "fcfe_re_g": {}, "blend_grid": {}},
        "valuation_confidence": {"fcff_dcf": "low", "fcfe_dcf": "blocked"},
        "formula_traces": [],
    }


def _blocked_policy():
    return build_valuation_publishability_policy(
        _dbd_like_artifact(), ticker="DBD", current_price_vnd=50_200.0
    )


def _blend() -> dict:
    return {
        "current_price_vnd": 50_200.0,
        "target_price_dcf_vnd": 27_207.0,
        "upside_pct": -0.458,
        "is_draft_only": True,
    }


def test_publishability_never_exposes_extreme_raw_target_as_headline():
    """A policy-blocked target is not substituted by a clamped-to-edge number.

    The raw FCFF (27,207, −46%) stays auditable inside the policy, but because the
    policy blocks it (market-sanity, no bridge) the report shows the market anchor,
    not a misleading −40% headline.
    """
    policy = _blocked_policy()
    assert policy.target_price_publishable is False  # internal metadata stays honest
    display = vm._report_display_governance("client_final", {}, _blend(), policy=policy)
    assert display["current_price"] == 50_200
    assert display["target_price"] == 50_200            # market anchor, not clamped raw
    assert display["upside"] == pytest.approx(0.0)
    assert display["raw_model_target"] is None          # blocked raw is not surfaced
    assert display["headline_target_governance"]["target_adjustment"] == "market_anchor_neutral"


def test_blocked_policy_rating_is_watch_not_a_clamped_call():
    policy = _blocked_policy()
    display = vm._report_display_governance("client_final", {}, _blend(), policy=policy)
    assert display["recommendation"] == "Theo dõi"


def test_recommendation_uses_watch_when_no_model_target_exists():
    assert vm._recommendation(None, "client_final", approved_for_display=False) == "Giữ"
    assert vm._recommendation(0.30, "client_final", approved_for_display=False) == "Mua"
    assert vm._recommendation(0.30, "client_final", approved_for_display=True) == "Mua"
    assert vm._recommendation(0.00, "client_final", has_model_value=False) == "Theo dõi"


def test_missing_raw_target_uses_neutral_headline_and_watch_rating():
    display = vm._report_display_governance(
        "client_final",
        {"current_price_vnd": 93_400.0},
        {},
        policy=None,
    )

    assert display["target_price"] == 93_400.0
    assert display["upside"] == 0.0
    assert display["recommendation"] == "Theo dõi"
    assert display["headline_target_governance"]["target_adjustment"] == "market_anchor_neutral"


def test_blocked_policy_surfaces_blocking_reasons():
    policy = _blocked_policy()
    display = vm._report_display_governance("client_final", {}, _blend(), policy=policy)
    # Cross-check multiples no longer hard-block; the genuine red flag for this
    # case is a DCF target far below market with no reconciling bridge.
    assert any("market_sanity" in r for r in display["blocking_reasons"])


def _clean_low_confidence_artifact() -> dict:
    # FCFF fully computed, DCF == market, only caveat is low confidence.
    return {
        "current_price_vnd": 100_000.0,
        "fcff": {
            "target_price_vnd": 100_000.0, "wacc": 0.12,
            "wacc_breakdown": {"risk_free_rate": 0.04},
            "fcff_table": [{"fcff": 10.0}], "equity_value": 13_000.0,
            "net_debt_bridge": {"net_debt": -100.0}, "ev_to_equity_bridge": {"ev": 12_000.0},
        },
        "fcfe": {"target_price_vnd": None, "fcfe_table": [{"fcfe": None, "net_borrowing": None}]},
        "blend_dcf": {"price_fcff_vnd": 100_000.0, "price_fcfe_vnd": None,
                      "target_price_dcf_vnd": 100_000.0, "is_draft_only": True},
        "sensitivity": {"fcff_wacc_g": {"a": {"x": 100.0, "y": 110.0}}, "fcfe_re_g": {}, "blend_grid": {}},
        "valuation_confidence": {"fcff_dcf": "low", "fcfe_dcf": "blocked"},
        "formula_traces": [{"method": "fcff"}],
    }


def test_publishable_policy_overrides_local_no_eligible_heuristic():
    """A clean low-confidence ticker (DCF == market, methods agree) is publishable
    per the single source of truth. The renderer must defer to the policy and not
    re-block it with its own confidence / draft-only heuristics."""
    policy = build_valuation_publishability_policy(
        _clean_low_confidence_artifact(), ticker="XYZ", current_price_vnd=100_000.0
    )
    assert policy.target_price_publishable is True  # sanity on the source of truth

    val_result = {
        "current_price": 100_000.0,
        "target_price": 100_000.0,
        "is_publishable": None,
        "valuation_method_policy": {"selected_methods": []},  # confidence-excluded
        "valuation_confidence": {"fcff_dcf": "low"},
    }
    blend = {"current_price_vnd": 100_000.0, "target_price_dcf_vnd": 100_000.0, "is_draft_only": True}
    display = vm._report_display_governance("client_final", val_result, blend, policy=policy)
    assert display["approved_for_display"] is True
    assert display["recommendation_publishable"] is True
    assert display["target_price"] == 100_000.0
    assert display["recommendation"] != "Chưa phát hành"
