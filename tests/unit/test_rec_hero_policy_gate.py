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


def test_blocked_policy_hides_hero_target():
    policy = _blocked_policy()
    assert policy.target_price_publishable is False
    display = vm._report_display_governance("client_final", {}, _blend(), policy=policy)
    assert display["target_price"] is None
    assert display["blend_target_price"] == 27_207
    assert display["approved_for_display"] is False


def test_blocked_policy_suppresses_official_recommendation():
    policy = _blocked_policy()
    display = vm._report_display_governance("client_final", {}, _blend(), policy=policy)
    assert display["recommendation"] == "Chưa phát hành"


def test_blocked_policy_surfaces_blocking_reasons():
    policy = _blocked_policy()
    display = vm._report_display_governance("client_final", {}, _blend(), policy=policy)
    assert any("divergence" in r for r in display["blocking_reasons"])
