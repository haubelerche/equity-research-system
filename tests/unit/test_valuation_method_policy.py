"""Tests for the single source of truth on valuation publishability.

These tests are deliberately ticker-agnostic. They prove the governance rules
are systemic, not DBD-specific: "a numeric output exists" must never imply
"this valuation is publishable".
"""
from __future__ import annotations

import pytest

from backend.valuation_method_policy import (
    ValuationPublishabilityPolicy,
    build_valuation_publishability_policy,
)


# --------------------------------------------------------------------------
# Synthetic artifact builders (no real ticker data; reusable fixtures)
# --------------------------------------------------------------------------
def _varying_grid() -> dict:
    return {"wacc_0.10": {"g_0.02": 100.0, "g_0.03": 110.0}, "wacc_0.11": {"g_0.02": 95.0, "g_0.03": 105.0}}


def _fcff(target=100000.0, confidence="high", *, trace=True, bridge=True, sens=True, varies=True):
    return {
        "target_price_vnd": target,
        "wacc": 0.12,
        "terminal_growth": 0.03,
        "wacc_breakdown": {"risk_free_rate": 0.04} if bridge else None,
        "fcff_table": [{"fcff": 10.0}] if trace else [],
        "equity_value": 13000.0 if bridge else None,
        "net_debt_bridge": {"net_debt": -100.0, "status": "ok"} if bridge else {},
        "ev_to_equity_bridge": {"ev": 12000.0} if bridge else None,
        "_confidence": confidence,
        "_trace": trace,
        "_sens": sens,
        "_varies": varies,
    }


def _fcfe(target=98000.0, *, blocked=False, confidence="high"):
    if blocked:
        return {
            "target_price_vnd": None,
            "fcfe_table": [{"fcfe": None, "net_borrowing": None}],
            "equity_value": 0.0,
            "warnings": ["FCFE BLOCKED — debt_schedule.is_fcfe_publishable = False"],
            "_confidence": "blocked",
        }
    return {
        "target_price_vnd": target,
        "fcfe_table": [{"fcfe": 12.0, "net_borrowing": 0.0}],
        "equity_value": 12500.0,
        "cost_of_equity_breakdown": {"risk_free_rate": 0.04},
        "warnings": [],
        "_confidence": confidence,
    }


def _artifact(
    *,
    fcff=None,
    fcfe=None,
    blend=None,
    pe_forward=None,
    core_pe=None,
    sensitivity=None,
    confidence=None,
    current_price=100000.0,
    traces=("fcff", "fcfe"),
):
    return {
        "ticker": "SYN",
        "current_price_vnd": current_price,
        "fcff": fcff if fcff is not None else _fcff(),
        "fcfe": fcfe if fcfe is not None else _fcfe(),
        "blend_dcf": blend if blend is not None else {
            "price_fcff_vnd": 100000.0, "price_fcfe_vnd": 98000.0,
            "target_price_dcf_vnd": 99200.0, "is_draft_only": False,
        },
        "pe_forward": pe_forward,
        "core_pe_net_cash": core_pe,
        "sensitivity": sensitivity if sensitivity is not None else {
            "fcff_wacc_g": _varying_grid(),
            "fcfe_re_g": _varying_grid(),
            "blend_grid": _varying_grid(),
        },
        "valuation_confidence": confidence if confidence is not None else {
            "fcff_dcf": "high", "fcfe_dcf": "high",
        },
        "formula_traces": [{"method": name} for name in traces],
    }


def _build(artifact, **kw):
    kw.setdefault("ticker", "SYN")
    kw.setdefault("current_price_vnd", (artifact or {}).get("current_price_vnd"))
    return build_valuation_publishability_policy(artifact, **kw)


# --------------------------------------------------------------------------
# Group A — Generic valuation policy
# --------------------------------------------------------------------------
def test_returns_policy_object():
    policy = _build(_artifact())
    assert isinstance(policy, ValuationPublishabilityPolicy)


def test_good_valuation_is_publishable():
    """Group C-4: everything present, sensitivity varies, divergence normal."""
    policy = _build(_artifact())
    assert policy.status == "publishable"
    assert policy.target_price_publishable is True
    assert policy.recommendation_publishable is True
    assert policy.target_price_vnd is not None


def test_low_confidence_fcff_cannot_be_primary():
    """Group A-1."""
    art = _artifact(
        fcff=_fcff(confidence="low"),
        fcfe=_fcfe(blocked=True),
        confidence={"fcff_dcf": "low", "fcfe_dcf": "blocked"},
        blend={"price_fcff_vnd": 100000.0, "price_fcfe_vnd": None,
               "target_price_dcf_vnd": 100000.0, "is_draft_only": True},
    )
    policy = _build(art)
    assert policy.primary_method != "FCFF"
    assert policy.target_price_publishable is False
    assert "low_confidence_primary_method" in policy.blocking_reasons


def test_blocked_fcfe_prevents_blended_final():
    """Group A-2 / C-2: FCFE blocked => blend not publishable."""
    art = _artifact(
        fcfe=_fcfe(blocked=True),
        confidence={"fcff_dcf": "high", "fcfe_dcf": "blocked"},
        blend={"price_fcff_vnd": 100000.0, "price_fcfe_vnd": None,
               "target_price_dcf_vnd": 100000.0, "is_draft_only": True},
        sensitivity={"fcff_wacc_g": _varying_grid(), "fcfe_re_g": {}, "blend_grid": {}},
    )
    policy = _build(art)
    blend = policy.method_diagnostics["BLEND"]
    assert blend.publishable is False
    assert "fcfe_unavailable_for_blend" in blend.blocking_reasons


def test_empty_blend_grid_blocks_blend():
    """Group A-3."""
    art = _artifact(sensitivity={
        "fcff_wacc_g": _varying_grid(), "fcfe_re_g": _varying_grid(), "blend_grid": {},
    })
    policy = _build(art)
    blend = policy.method_diagnostics["BLEND"]
    assert blend.publishable is False
    assert "blend_sensitivity_missing_or_constant" in blend.blocking_reasons


def test_critical_divergence_blocks_target_and_recommendation():
    """Group A-4 / C-1 (DBD-like): FCFF 27k, P/E 49k, core P/E 63k, price 50k."""
    art = _artifact(
        current_price=50200.0,
        fcff=_fcff(target=27207.0, confidence="low"),
        fcfe=_fcfe(blocked=True),
        confidence={"fcff_dcf": "low", "fcfe_dcf": "blocked"},
        blend={"price_fcff_vnd": 27207.0, "price_fcfe_vnd": None,
               "target_price_dcf_vnd": 27207.0, "is_draft_only": True},
        pe_forward={"target_price_vnd": 49336.0},
        core_pe={"target_price_vnd": 63246.0},
        sensitivity={"fcff_wacc_g": _varying_grid(), "fcfe_re_g": {}, "blend_grid": {}},
    )
    policy = _build(art)
    assert policy.divergence_pct is not None and policy.divergence_pct > 0.80
    assert policy.target_price_publishable is False
    assert policy.recommendation_publishable is False
    assert "valuation_method_divergence_critical" in policy.blocking_reasons
    # The 27,207 must not become the official headline target.
    assert policy.target_price_vnd is None


def test_market_sanity_break_without_bridge_blocks_recommendation():
    """Group A-5: primary target diverges >40% from price with no bridge."""
    art = _artifact(
        current_price=100000.0,
        fcff=_fcff(target=40000.0, bridge=False),  # 60% below price, no bridge
        fcfe=_fcfe(blocked=True),
        confidence={"fcff_dcf": "high", "fcfe_dcf": "blocked"},
        blend={"price_fcff_vnd": 40000.0, "price_fcfe_vnd": None,
               "target_price_dcf_vnd": 40000.0, "is_draft_only": True},
    )
    policy = _build(art)
    assert policy.recommendation_publishable is False
    assert "market_sanity_bridge_missing" in policy.blocking_reasons


def test_missing_wacc_decomposition_excludes_fcff():
    """Group A-6."""
    art = _artifact(fcff=_fcff(bridge=False))
    policy = _build(art)
    fcff = policy.method_diagnostics["FCFF"]
    assert fcff.publishable is False
    assert fcff.bridge_present is False


def test_missing_formula_trace_excludes_method():
    """Group A-8."""
    art = _artifact(fcff=_fcff(trace=False), traces=("fcfe",))
    policy = _build(art)
    fcff = policy.method_diagnostics["FCFF"]
    assert fcff.formula_trace_present is False
    assert fcff.publishable is False
    assert "formula_trace_missing" in fcff.blocking_reasons


def test_missing_artifact_is_blocked_not_borrowed():
    """Group A-9 / C-3: ticker with no artifact."""
    policy = build_valuation_publishability_policy(None, ticker="ZZZ")
    assert policy.status == "missing_artifact"
    assert policy.target_price_publishable is False
    assert policy.recommendation_publishable is False
    assert "valuation_artifact_missing_for_ticker" in policy.blocking_reasons
    assert policy.target_price_vnd is None


def test_excluded_methods_are_not_recommendation_drivers():
    """Group A-10: cross-check P/E methods never drive primary/recommendation."""
    art = _artifact(
        fcff=_fcff(confidence="low"),
        fcfe=_fcfe(blocked=True),
        confidence={"fcff_dcf": "low", "fcfe_dcf": "blocked"},
        blend={"price_fcff_vnd": 100000.0, "price_fcfe_vnd": None,
               "target_price_dcf_vnd": 100000.0, "is_draft_only": True},
        pe_forward={"target_price_vnd": 99000.0},
    )
    policy = _build(art)
    pe = policy.method_diagnostics.get("PE_FORWARD")
    assert pe is None or pe.role in {"cross_check", "scenario_only", "excluded"}
    assert policy.primary_method not in {"PE_FORWARD", "CORE_PE_NET_CASH"}


def test_to_dict_is_json_serialisable():
    import json
    policy = _build(_artifact())
    payload = policy.to_dict()
    json.dumps(payload)
    assert payload["status"] == "publishable"
    assert "method_diagnostics" in payload
