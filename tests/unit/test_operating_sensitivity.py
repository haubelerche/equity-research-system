"""Tests for build_operating_sensitivity_table in sensitivity.py (Phase 5)."""
from __future__ import annotations

import json
import pytest
from backend.analytics.sensitivity import build_operating_sensitivity_table
from backend.analytics.fcff import WACCAssumptions


def _ft() -> dict:
    return {
        "revenue.net": {"2023FY": 1500.0, "2024FY": 1700.0, "2025FY": 1865.0},
        "gross_profit.total": {"2023FY": 680.0, "2024FY": 780.0, "2025FY": 884.0},
        "sga.total": {"2023FY": -350.0, "2024FY": -380.0, "2025FY": -418.0},
        "depreciation.total": {"2023FY": 40.0, "2024FY": 44.0, "2025FY": 48.0},
        "capex.total": {"2023FY": -80.0, "2024FY": -90.0, "2025FY": -100.0},
        "total_debt.ending": {"2025FY": 43.0},
        "cash_and_equivalents.ending": {"2025FY": 120.0},
        "equity.parent": {"2025FY": 1500.0},
        "total_assets.ending": {"2025FY": 2500.0},
        "profit_before_tax.total": {"2023FY": 290.0, "2024FY": 320.0, "2025FY": 346.0},
        "tax_expense.total": {"2023FY": -50.0, "2024FY": -55.0, "2025FY": -54.0},
        "net_income.parent": {"2023FY": 240.0, "2024FY": 265.0, "2025FY": 292.0},
    }


def _build_base_forecast():
    from backend.analytics.forecasting import run_forecast
    return run_forecast("TST", _ft(), shares_mn=94.45)


class TestOperatingSensitivity:
    def _table(self, rev_range=None, gm_range=None):
        from backend.analytics.forecasting import run_forecast
        base = run_forecast("TST", _ft(), shares_mn=94.45)
        return build_operating_sensitivity_table(
            ticker="TST",
            fact_table=_ft(),
            base_forecast=base,
            base_wacc_assumptions=WACCAssumptions(wacc_override=0.13),
            revenue_growth_range=rev_range or [0.03, 0.07, 0.11],
            gross_margin_range=gm_range or [0.40, 0.46, 0.52],
            shares_mn=94.45,
            current_price_vnd=50_000.0,
        )

    def test_matrix_has_correct_row_count(self):
        t = self._table(rev_range=[0.03, 0.07, 0.11])
        assert len(t["matrix"]) == 3

    def test_matrix_has_correct_column_count(self):
        t = self._table(gm_range=[0.40, 0.46, 0.52])
        for row_vals in t["matrix"].values():
            assert len(row_vals) == 3

    def test_higher_margin_gives_higher_price(self):
        t = self._table(
            rev_range=[0.07],
            gm_range=[0.35, 0.45, 0.55],
        )
        prices = list(list(t["matrix"].values())[0].values())
        # Not all may be non-None, but non-None prices should increase
        non_null = [p for p in prices if p is not None]
        if len(non_null) >= 2:
            assert non_null[-1] > non_null[0]

    def test_base_growth_and_margin_in_output(self):
        t = self._table()
        assert "base_revenue_growth" in t
        assert "base_gross_margin" in t

    def test_formula_in_output(self):
        t = self._table()
        assert "formula" in t
        assert "revenue_growth" in t["formula"]

    def test_output_serializable(self):
        t = self._table()
        json.dumps(t)

    def test_unit_is_vnd_per_share(self):
        t = self._table()
        assert "VND/share" in t["unit"]

    def test_default_ranges_center_on_base_drivers(self):
        from backend.analytics.forecasting import run_forecast
        base = run_forecast("TST", _ft(), shares_mn=94.45)
        t = build_operating_sensitivity_table(
            ticker="TST",
            fact_table=_ft(),
            base_forecast=base,
            base_wacc_assumptions=WACCAssumptions(wacc_override=0.13),
            shares_mn=94.45,
        )
        # Base revenue CAGR should appear in the range
        if base.revenue_cagr is not None:
            cagr = round(base.revenue_cagr, 4)
            rev_range = t["revenue_growth_range"]
            # Allow small float rounding tolerance
            assert any(abs(r - cagr) < 0.001 for r in rev_range)
