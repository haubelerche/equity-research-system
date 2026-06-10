from __future__ import annotations

from backend.harness.gates import valuation_gate, valuation_reconciliation_gate


def test_valuation_gate_passes_when_fcff_valid_without_fcfe():
    """When FCFF is present and valid, valuation gate passes even without FCFE."""
    summary = {
        "has_fcff": True,
        "has_fcfe": False,
        "has_blend": True,
        "has_sensitivity": True,
        "formula_version": "v2",
        "assumption_version": "v1",
        "unit_policy": "VND",
        "currency": "VND",
        "period_scope": "FY",
        "assumptions": {"wacc": 0.138},
        "sensitivity_summary": {"rows": 5, "cols": 5},
        "valuation_methods": ["FCFF", "PE_FORWARD"],
        "snapshot_id": "snap_abc",
        "assumption_gate": {"status": "draft_needs_analyst_review"},
    }
    gate = valuation_gate(summary)
    assert gate["passed"] is True


def test_valuation_gate_fails_when_fcff_missing():
    """If FCFF itself is missing, that's still a blocker."""
    summary = {
        "has_fcff": False,
        "has_fcfe": False,
        "has_blend": False,
        "has_sensitivity": True,
        "formula_version": "v2",
        "assumption_version": "v1",
        "unit_policy": "VND",
        "currency": "VND",
        "period_scope": "FY",
        "assumptions": {"wacc": 0.138},
        "sensitivity_summary": {"rows": 5, "cols": 5},
        "valuation_methods": ["FCFF"],
        "snapshot_id": "snap_abc",
        "assumption_gate": {"status": "draft"},
    }
    gate = valuation_gate(summary)
    assert gate["passed"] is False


def test_valuation_reconciliation_gate_warning_when_fcfe_missing_fcff_complete():
    """When FCFE bridge is missing but FCFF is complete, severity is 'warning' not 'critical'."""
    valuation = {
        "fcff": {
            "projected_fcff": [100, 110],
            "pv_of_fcff": [90, 95],
            "terminal_value": 1000,
            "pv_of_terminal_value": 600,
            "enterprise_value": 785,
            "cash_and_short_term_investments": 130,
            "debt": 0,
            "equity_value": 915,
            "shares_outstanding": 130.7,
            "value_per_share": 7000,
        },
        "fcfe": {},
        "key_assumptions": {
            "wacc": 0.138,
            "risk_free_rate": 0.03,
            "equity_risk_premium": 0.08,
            "beta": 0.9,
            "cost_of_equity": 0.102,
            "cost_of_debt": 0.06,
            "tax_rate": 0.2,
            "terminal_growth": 0.03,
        },
        "selected_methods": ["FCFF"],
        "method_weights": {"FCFF": 1.0},
        "weighted_target_price": {"target_price": 7000},
        "sensitivity": {"rows": 5},
        "sanity_checks": {"market_cap_check": {"passed": True}},
        "approved_assumption_refs": ["ref1"],
        "current_price": 5000,
        "upside_downside_vs_current_price": 0.40,
        "recommendation": "BUY",
    }
    gate = valuation_reconciliation_gate(valuation)
    # Should pass with warning, not fail
    assert gate["passed"] is True
    assert gate["severity"] == "warning"


def test_valuation_reconciliation_gate_fails_when_fcff_incomplete():
    """When FCFF bridge is also incomplete, that's still a critical failure."""
    valuation = {
        "fcff": {"projected_fcff": [100]},  # missing most required fields
        "fcfe": {},
        "key_assumptions": {},
        "weighted_target_price": {},
    }
    gate = valuation_reconciliation_gate(valuation)
    assert gate["passed"] is False
