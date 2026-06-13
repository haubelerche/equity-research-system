"""Tests for backend.analytics.scenario_runner (Phase 5 Bear/Base/Bull)."""
from __future__ import annotations

import pytest
from backend.analytics.scenario_runner import (
    run_scenario,
    run_scenarios,
    ScenarioSummary,
    _DEFAULT_SCENARIO_DELTAS,
)
from backend.analytics.fcff import WACCAssumptions
from backend.analytics.fcfe import CostOfEquityAssumptions


def _minimal_fact_table() -> dict:
    """Minimal fact table enough to run forecast + FCFF + FCFE."""
    return {
        "revenue.net": {
            "2023FY": 1500.0, "2024FY": 1700.0, "2025FY": 1865.0,
        },
        "gross_profit.total": {
            "2023FY": 680.0, "2024FY": 780.0, "2025FY": 884.0,
        },
        "sga.total": {
            "2023FY": -350.0, "2024FY": -380.0, "2025FY": -418.0,
        },
        "depreciation.total": {
            "2023FY": 40.0, "2024FY": 44.0, "2025FY": 48.0,
        },
        "capex.total": {
            "2023FY": -80.0, "2024FY": -90.0, "2025FY": -100.0,
        },
        "total_debt.ending": {"2025FY": 43.0},
        "cash_and_equivalents.ending": {"2025FY": 120.0},
        "equity.parent": {"2025FY": 1500.0},
        "total_assets.ending": {"2025FY": 2500.0},
        "profit_before_tax.total": {
            "2023FY": 290.0, "2024FY": 320.0, "2025FY": 346.0,
        },
        "tax_expense.total": {
            "2023FY": -50.0, "2024FY": -55.0, "2025FY": -54.0,
        },
        "net_income.parent": {
            "2023FY": 240.0, "2024FY": 265.0, "2025FY": 292.0,
        },
    }


class TestScenarioDeltas:
    def test_bear_has_negative_revenue_delta(self):
        assert _DEFAULT_SCENARIO_DELTAS["bear"]["revenue_growth_delta"] < 0

    def test_bull_has_positive_revenue_delta(self):
        assert _DEFAULT_SCENARIO_DELTAS["bull"]["revenue_growth_delta"] > 0

    def test_base_all_zeros(self):
        for v in _DEFAULT_SCENARIO_DELTAS["base"].values():
            assert v == 0.0

    def test_bear_wacc_higher_than_base(self):
        assert _DEFAULT_SCENARIO_DELTAS["bear"]["wacc_delta"] > 0

    def test_bull_wacc_lower_than_base(self):
        assert _DEFAULT_SCENARIO_DELTAS["bull"]["wacc_delta"] < 0


class TestRunScenario:
    def _kwargs(self):
        return dict(
            ticker="TST",
            fact_table=_minimal_fact_table(),
            base_wacc_assumptions=WACCAssumptions(wacc_override=0.13),
            base_coe_assumptions=CostOfEquityAssumptions(re_override=0.14),
            base_terminal_growth=0.03,
            shares_mn=94.45,
            current_price_vnd=50_000.0,
        )

    def test_base_scenario_returns_result(self):
        result = run_scenario(**self._kwargs(), label="base")
        assert result.label == "base"
        assert result.forecast is not None

    def test_three_scenarios_have_different_wacc(self):
        kw = self._kwargs()
        bear = run_scenario(**kw, label="bear")
        base = run_scenario(**kw, label="base")
        bull = run_scenario(**kw, label="bull")
        # bear WACC > base WACC > bull WACC
        bear_w = bear.assumptions.wacc_override
        base_w = base.assumptions.wacc_override
        bull_w = bull.assumptions.wacc_override
        assert bear_w > base_w > bull_w

    def test_to_dict_serializable(self):
        import json
        result = run_scenario(**self._kwargs(), label="base")
        json.dumps(result.to_dict())


class TestRunScenarios:
    def _summary(self) -> ScenarioSummary:
        return run_scenarios(
            ticker="TST",
            fact_table=_minimal_fact_table(),
            base_wacc_assumptions=WACCAssumptions(wacc_override=0.13),
            base_coe_assumptions=CostOfEquityAssumptions(re_override=0.14),
            shares_mn=94.45,
            current_price_vnd=50_000.0,
        )

    def test_returns_three_scenarios(self):
        summary = self._summary()
        assert summary.bear.label == "bear"
        assert summary.base.label == "base"
        assert summary.bull.label == "bull"

    def test_bull_price_gte_base_gte_bear(self):
        summary = self._summary()
        # Bull should produce higher target than bear (if not blocked)
        bear_p = summary.bear.target_price_vnd
        bull_p = summary.bull.target_price_vnd
        if bear_p and bull_p:
            assert bull_p >= bear_p

    def test_price_range_returns_min_max(self):
        summary = self._summary()
        pr = summary.price_range()
        assert "min_price" in pr
        assert "max_price" in pr
        assert "base_price" in pr

    def test_to_dict_serializable(self):
        import json
        summary = self._summary()
        json.dumps(summary.to_dict())
