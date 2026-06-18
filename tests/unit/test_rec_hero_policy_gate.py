"""Group B — renderer must respect ValuationPublishabilityPolicy.

The report view model must not promote a non-publishable valuation into the
hero target price or a BUY/HOLD/SELL recommendation, even when a numeric value
is technically available in the blend artifact.
"""
from __future__ import annotations

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


def test_publishability_never_blanks_computed_target():
    """Option B: publication readiness is internal metadata only. A valuation
    report must always present its computed target price — the gate never blanks
    the client-facing number (a report with no target is useless)."""
    policy = _blocked_policy()
    assert policy.target_price_publishable is False  # internal metadata stays honest
    display = vm._report_display_governance("client_final", {}, _blend(), policy=policy)
    assert display["target_price"] == 27_207
    assert display["current_price"] == 50_200
    assert display["upside"] is not None
    assert display["approved_for_display"] is True
    assert display["recommendation_publishable"] is False


def test_blocked_policy_uses_review_status_not_sell_rating():
    policy = _blocked_policy()
    display = vm._report_display_governance("client_final", {}, _blend(), policy=policy)
    # 27,207 target vs 50,200 price still remains visible, but the policy
    # blocker suppresses an official Buy/Hold/Sell rating.
    assert display["recommendation"] == "Đang rà soát"


def test_recommendation_only_unrated_when_no_target_at_all():
    # The Not-Rated label appears only when there is genuinely no computed value.
    assert vm._recommendation(None, "client_final", approved_for_display=False) == "Không xếp hạng"
    assert vm._recommendation(0.30, "client_final", approved_for_display=False) == "Đang rà soát"
    assert vm._recommendation(0.30, "client_final", approved_for_display=True) == "Mua"


def test_blocked_policy_surfaces_blocking_reasons():
    policy = _blocked_policy()
    display = vm._report_display_governance("client_final", {}, _blend(), policy=policy)
    assert any("divergence" in r for r in display["blocking_reasons"])


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
