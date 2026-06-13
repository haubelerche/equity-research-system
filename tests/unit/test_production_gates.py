from __future__ import annotations

from copy import deepcopy

from backend.harness.gates import (
    forecast_quality_gate,
    report_completeness_gate,
    senior_critic_gate,
    valuation_reconciliation_gate,
)


def _forecast_model() -> dict:
    checks = {
        "historical_continuity_check": "pass",
        "driver_support_check": "pass",
        "margin_sanity_check": "pass",
        "balance_sheet_balance_check": "pass",
        "cash_flow_consistency_check": "pass",
    }
    return {
        "revenue_forecast": {
            "by_channel": {"etc": {"forecast": {"2026F": 100}, "drivers": ["tender_value"]}},
            "by_product_group": {"oncology": {"forecast": {"2026F": 60}, "drivers": ["market_share"]}},
        },
        "gross_margin_forecast": {"assumptions": {"product_mix": "oncology growth"}, "forecast": {"2026F": 0.45}},
        "opex_forecast": {
            "selling_expense": {"2026F": 10},
            "admin_expense": {"2026F": 8},
            "assumptions": {"selling_ratio": 0.1},
        },
        "working_capital_forecast": {"receivable_days": 60, "inventory_days": 90, "payable_days": 30},
        "capex_and_depreciation": {"capex_projects": ["EU-GMP"], "depreciation": {"2026F": 5}},
        "debt_cash_interest": {
            "cash": {"2026F": 30},
            "short_term_debt": {"2026F": 10},
            "long_term_debt": {"2026F": 20},
            "interest_expense": {"2026F": 2},
            "net_borrowing": {"2026F": 1},
        },
        "eps_forecast": {"2026F": 3.2},
        "forecast_financial_summary": {"income_statement": {"2026F": {}}},
        "forecast_quality_checks": checks,
    }


def _valuation() -> dict:
    return {
        "selected_methods": ["FCFF", "FCFE"],
        "method_weights": {"FCFF": 50, "FCFE": 50},
        "approved_assumption_refs": ["approval_1"],
        "key_assumptions": {
            "risk_free_rate": 0.04,
            "equity_risk_premium": 0.08,
            "beta": 1.0,
            "cost_of_equity": 0.12,
            "cost_of_debt": 0.07,
            "tax_rate": 0.2,
            "wacc": 0.1,
            "terminal_growth": 0.03,
            "net_borrowing": {"2026F": 1},
        },
        "fcff": {
            "projected_fcff": {"2026F": 10},
            "pv_of_fcff": 40,
            "terminal_value": 100,
            "pv_of_terminal_value": 60,
            "enterprise_value": 100,
            "cash_and_short_term_investments": 20,
            "debt": 20,
            "equity_value": 100,
            "shares_outstanding": 10,
            "value_per_share": 10,
        },
        "fcfe": {
            "projected_fcfe": {"2026F": 11},
            "pv_of_fcfe": 45,
            "terminal_value": 100,
            "pv_of_terminal_value": 65,
            "equity_value": 110,
            "shares_outstanding": 10,
            "value_per_share": 11,
        },
        "weighted_target_price": {"raw": 10.5, "rounded": 10.5, "upside_downside_vs_current_price": 0.05},
        "current_price": 10,
        "recommendation": "HOLD",
        "sensitivity": {"wacc_vs_terminal_growth": [[10.5]]},
        "sanity_checks": {"target_price_reconciliation": "pass", "pe_implied": 12.0},
    }


def _report() -> dict:
    sections = {
        "cover_investment_summary": {"text": "summary"},
        "company_overview": {"text": "overview"},
        "recent_financial_performance": {"text": "financials"},
        "driver_based_forecast": {"text": "forecast"},
        "valuation_and_recommendation": {"text": "valuation"},
        "risks_and_monitoring_factors": {"text": "risks"},
        "forecast_financial_summary": {"text": "statements"},
    }
    tables = [
        "trading_snapshot", "company_overview", "recent_financial_results",
        "business_plan_completion", "forecast_assumptions", "valuation_summary",
        "dcf_assumptions", "fcff_fcfe_bridge", "forecast_financial_statement_summary",
        "risk_and_monitoring_factors",
    ]
    charts = [
        "stock_price_vs_benchmark", "revenue_by_channel",
        "product_group_revenue_or_market_share", "gross_margin_net_margin_trend",
        "forecast_revenue", "forecast_gross_profit_or_margin",
    ]
    return {"sections": sections, "required_tables": tables, "required_charts": charts}


def _critic_review() -> dict:
    metrics = {
        "thesis_strength": 8,
        "driver_logic": 8,
        "forecast_consistency": 8,
        "valuation_coherence": 8,
        "evidence_depth": 7.5,
        "sector_specificity": 8,
        "risk_balance": 7.5,
        "table_chart_completeness": 8,
        "narrative_quality": 8,
        "numeric_integrity": 9.5,
        "citation_integrity": 9.5,
    }
    return {
        "decision": "pass",
        "scorecard": {key: {"score": score, "explanation": "meets rubric"} for key, score in metrics.items()},
        "findings": [{"finding_id": "low_1", "severity": "low"}],
    }


def test_forecast_quality_gate_passes_complete_driver_based_model() -> None:
    assert forecast_quality_gate(_forecast_model())["passed"]


def test_forecast_quality_gate_blocks_missing_driver_and_failed_balance_check() -> None:
    model = _forecast_model()
    model["revenue_forecast"]["by_channel"]["etc"]["drivers"] = []
    model["forecast_quality_checks"]["balance_sheet_balance_check"] = "fail"
    model["abnormal_growth_flags"] = [{"metric": "revenue.etc", "explained": False}]

    result = forecast_quality_gate(model)

    assert not result["passed"]
    assert "revenue_forecast_by_channel_drivers_missing:etc" in result["blocking_reasons"]
    assert "forecast_quality_check_failed:balance_sheet_balance_check" in result["blocking_reasons"]
    assert "unexplained_abnormal_forecast_growth" in result["blocking_reasons"]


def test_valuation_reconciliation_gate_passes_reconciled_artifact() -> None:
    assert valuation_reconciliation_gate(_valuation())["passed"]


def test_valuation_reconciliation_gate_accepts_vnd_bn_and_mn_share_units() -> None:
    valuation = _valuation()
    valuation["fcff"]["equity_value"] = 100
    valuation["fcff"]["shares_outstanding"] = 10
    valuation["fcff"]["value_per_share"] = 10_000
    valuation["fcff"]["enterprise_value"] = 80
    valuation["fcff"]["cash_and_short_term_investments"] = 20
    valuation["fcff"]["debt"] = 0
    valuation["fcfe"]["equity_value"] = 110
    valuation["fcfe"]["shares_outstanding"] = 10
    valuation["fcfe"]["value_per_share"] = 11_000
    valuation["weighted_target_price"]["raw"] = 10_500
    valuation["weighted_target_price"]["rounded"] = 10_500
    valuation["weighted_target_price"]["upside_downside_vs_current_price"] = 0.05
    valuation["current_price"] = 10_000

    assert valuation_reconciliation_gate(valuation)["passed"]


def test_valuation_reconciliation_gate_blocks_target_upside_and_recommendation_mismatch() -> None:
    valuation = _valuation()
    valuation["weighted_target_price"]["raw"] = 12
    valuation["recommendation"] = "SELL"
    valuation["fcff"]["equity_value"] = 90

    result = valuation_reconciliation_gate(valuation)

    assert not result["passed"]
    assert "fcff_equity_bridge_not_reconciled" in result["blocking_reasons"]
    assert "fcff_value_per_share_not_reconciled" in result["blocking_reasons"]
    assert "weighted_target_price_not_reconciled" in result["blocking_reasons"]
    assert "upside_downside_not_reconciled" in result["blocking_reasons"]
    assert "recommendation_not_reconciled" in result["blocking_reasons"]


def test_report_completeness_gate_accepts_explicit_insufficient_evidence() -> None:
    report = _report()
    report["required_charts"] = [
        item for item in report["required_charts"] if item != "stock_price_vs_benchmark"
    ] + [{"chart_id": "stock_price_vs_benchmark", "status": "insufficient_evidence"}]

    assert report_completeness_gate(report)["passed"]


def test_report_completeness_gate_blocks_missing_section_table_and_chart() -> None:
    report = _report()
    del report["sections"]["driver_based_forecast"]
    report["required_tables"].remove("valuation_summary")
    report["required_charts"].remove("forecast_gross_profit_or_margin")

    result = report_completeness_gate(report)

    assert not result["passed"]
    assert "driver_based_forecast" in result["summary"]["missing_sections"]
    assert "valuation_summary" in result["summary"]["missing_tables"]
    assert "forecast_gross_profit_or_margin" in result["summary"]["missing_charts"]


def test_senior_critic_gate_passes_minimum_thresholds() -> None:
    assert senior_critic_gate(_critic_review())["passed"]


def test_senior_critic_gate_blocks_low_integrity_score_and_critical_finding() -> None:
    review = deepcopy(_critic_review())
    review["decision"] = "revision_required"
    review["scorecard"]["numeric_integrity"]["score"] = 9.4
    review["findings"].append({"finding_id": "critical_1", "severity": "critical"})

    result = senior_critic_gate(review)

    assert not result["passed"]
    assert "critic_decision_not_pass:revision_required" in result["blocking_reasons"]
    assert any(reason.startswith("critic_scores_below_threshold:") for reason in result["blocking_reasons"])
    assert "blocking_critic_findings:critical_1" in result["blocking_reasons"]
