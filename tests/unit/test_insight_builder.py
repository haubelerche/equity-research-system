"""Deterministic research insight pack — analyst-grade 'so what' from existing numbers.

Each insight ties a claim to evidence_refs ([1] data, [2] model, [3]+ news) and a
valuation_implication. Insights with missing inputs are 'insufficient_evidence', not faked.
"""
from __future__ import annotations

from backend.reporting.insight_builder import build_insight_pack


def _inputs(**over) -> dict:
    base = dict(
        revenue_growth_latest=0.04,
        profit_growth_latest=0.54,
        gross_margin_latest=0.46,
        gross_margin_prev=0.44,
        net_debt_ebitda=-1.8,
        upside=0.139,
        recommendation="NẮM GIỮ",
        news_count=8,
    )
    base.update(over)
    return base


def test_growth_quality_flags_cost_driven_when_profit_outpaces_revenue() -> None:
    pack = build_insight_pack(_inputs())
    growth = next(i for i in pack if i["section"] == "growth")
    assert growth["status"] == "ready"
    assert "[1]" in growth["evidence_refs"]
    assert growth["valuation_implication"]  # non-empty 'so what'
    # Profit (54%) >> revenue (4%) → cost/margin-driven, caution on terminal growth.
    assert "biên" in growth["claim"].lower() or "chi phí" in growth["claim"].lower()


def test_net_cash_leverage_insight() -> None:
    pack = build_insight_pack(_inputs(net_debt_ebitda=-1.8))
    lev = next(i for i in pack if i["section"] == "leverage")
    assert lev["status"] == "ready"
    assert "tiền" in lev["claim"].lower()  # net cash position


def test_valuation_insight_uses_model_evidence_and_recommendation() -> None:
    pack = build_insight_pack(_inputs(upside=0.139, recommendation="NẮM GIỮ"))
    val = next(i for i in pack if i["section"] == "valuation")
    assert "[2]" in val["evidence_refs"]
    assert "NẮM GIỮ" in val["valuation_implication"]


def test_missing_inputs_yield_insufficient_evidence_not_fabrication() -> None:
    pack = build_insight_pack(_inputs(gross_margin_latest=None, gross_margin_prev=None))
    margin = next(i for i in pack if i["section"] == "margin")
    assert margin["status"] == "insufficient_evidence"
    assert "gross_margin_latest" in margin["missing_fields"]


def test_catalyst_insight_only_when_news_present() -> None:
    assert any(i["section"] == "catalyst" for i in build_insight_pack(_inputs(news_count=8)))
    assert not any(i["section"] == "catalyst" for i in build_insight_pack(_inputs(news_count=0)))
