"""Tests for the deterministic, artifact-grounded narrative builder (Phase 07)."""
from __future__ import annotations

from backend.reporting.narrative_builder import NarrativeInputs, build_all


def _inputs() -> NarrativeInputs:
    return NarrativeInputs(
        ticker="DBD", company_name="Công ty CP Dược Bình Định",
        revenue_latest=1865.0, revenue_prev=1727.0, revenue_growth_latest=0.08, revenue_cagr=0.063,
        net_income_latest=292.0, net_margin_latest=0.157, gross_margin_latest=0.474, eps_latest=3000.0,
        cash_conversion=2.1, rev_growth_driver=0.0626, gross_margin_driver=0.4827, sga_driver=0.2286,
        capex_driver=0.0835, tax_driver=0.1579, wacc=0.138, terminal_growth=0.03,
        current_price=50200.0, target_price=30409.0, upside=-0.394, rating="BÁN",
        price_fcff=35767.0, price_fcfe=22372.0, sens_low=39679.0, sens_high=91113.0, dividend_yield=0.02,
    )


def test_all_sections_meet_min_length():
    sections = build_all(_inputs())
    assert set(sections) == {
        "investment_thesis", "latest_business_update", "financial_performance",
        "forecast_valuation_narrative", "valuation_narrative", "risks_catalysts",
    }
    for name, text in sections.items():
        assert len(text.split()) >= 280, f"{name} too short: {len(text.split())} words"


def test_sections_contain_real_numbers():
    sections = build_all(_inputs())
    thesis = sections["investment_thesis"]
    assert "1,865 tỷ đồng" in thesis       # revenue
    assert "47.4%" in thesis               # gross margin
    assert "30,409 VND" in thesis          # target price


def test_missing_inputs_say_so_not_fabricate():
    # No valuation inputs -> must not invent a target price
    n = NarrativeInputs(ticker="ZZZ", company_name="Test Co")
    val = build_all(n)["valuation_narrative"]
    assert "chưa đủ dữ liệu" in val
    # No fabricated VND figure for target when target_price is None
    assert "giá mục tiêu hợp nhất hiện" in val.lower()
