from __future__ import annotations

from backend.valuation.audit import build_market_sanity_bridge, build_valuation_audit


def _artifact() -> dict:
    return {
        "ticker": "PMC",
        "snapshot_id": "snap-1",
        "generated_at": "2026-06-17T00:00:00+00:00",
        "formula_version": "valuation_v1_code_first_fcff_fcfe_blend",
        "current_price_vnd": 100_000.0,
        "fcff": {
            "target_price_vnd": 50_000.0,
            "wacc": 0.12,
            "terminal_growth": 0.03,
            "wacc_breakdown": {
                "risk_free_rate": 0.04,
                "beta": 0.9,
                "equity_risk_premium": 0.08,
                "size_premium": 0.0,
                "specific_risk_premium": 0.008,
                "cost_of_equity": 0.12,
                "cost_of_debt": 0.08,
                "tax_rate": 0.2,
                "wacc": 0.12,
            },
            "equity_value": 5000.0,
            "shares_mn": 100.0,
            "net_debt_bridge": {"status": "ok"},
            "ev_to_equity_bridge": {"ev": 5000.0},
        },
        "fcfe": {
            "target_price_vnd": None,
            "fcfe_table": [{"fcfe": None, "net_borrowing": None}],
        },
        "blend_dcf": {
            "price_fcff_vnd": 50_000.0,
            "price_fcfe_vnd": None,
            "target_price_dcf_vnd": 50_000.0,
            "current_price_vnd": 100_000.0,
            "upside_pct": -0.5,
            "is_draft_only": True,
        },
        "pe_forward": {"eps_fy1_vnd": 4_000.0, "target_pe": 15.0, "price_pe_forward_vnd": None},
        "valuation_confidence": {"fcff_dcf": "high", "fcfe_dcf": "blocked"},
        "formula_traces": [{"formula_id": "fcff"}],
        "sensitivity": {
            "fcff_wacc_g": {"wacc_0.11": {"g_0.02": 55_000, "g_0.03": 50_000}},
            "fcfe_re_g": {},
            "blend_grid": {},
        },
        "method_weights": {"FCFF": 100.0, "FCFE": 40.0},
        "assumption_gate": {
            "recommendation_allowed": False,
            "blocking_reasons": ["Final recommendation has not been explicitly approved by analyst."],
        },
    }


def test_valuation_audit_blocks_systemic_pmc_like_failures():
    audit = build_valuation_audit(_artifact(), ticker="PMC", run_id="run-pmc")

    codes = {error["code"] for error in audit["errors"]}
    assert "MULTIPLES_FALLBACK_ERROR" in codes
    assert "METHOD_ELIGIBILITY_ERROR" in codes
    assert "MARKET_SANITY_ERROR" in codes
    assert "RECOMMENDATION_GATE_ERROR" in codes
    assert audit["recommendation_status"] == {
        "recommendation": "Chưa phát hành",
        "target_price_status": "Không đủ điều kiện công bố",
        "report_status": "Draft-only",
        "draft_only": True,
    }


def test_market_sanity_bridge_exposes_required_cross_checks():
    bridge = build_market_sanity_bridge(_artifact())

    assert bridge["target_to_market"] == 0.5
    assert bridge["upside_downside"] == -0.5
    assert bridge["target_pe_implied"] == 12.5
    assert bridge["thresholds"]["requires_bridge"] is True
