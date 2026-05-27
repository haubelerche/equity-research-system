"""Unit tests for backend/analytics/ratios.py.

Tests: compute_ratios, ratio_table_for_display.
No DB required — all in-memory.
"""
from __future__ import annotations

import pytest

from backend.analytics.ratios import compute_ratios, ratio_table_for_display


def _base_table() -> dict:
    return {
        "revenue.net":               {"2022FY": 4000.0, "2023FY": 5000.0},
        "gross_profit.total":        {"2022FY": 1600.0, "2023FY": 2000.0},
        "net_income.parent":         {"2022FY":  400.0, "2023FY":  600.0},
        "ebitda.total":              {"2022FY":  800.0, "2023FY": 1000.0},
        "equity.parent":             {"2022FY": 2000.0, "2023FY": 2400.0},
        "total_assets.ending":       {"2022FY": 3000.0, "2023FY": 3600.0},
        "total_debt.ending":         {"2022FY":  400.0, "2023FY":  500.0},
        "operating_cash_flow.total": {"2022FY":  500.0, "2023FY":  700.0},
        "capex.total":               {"2022FY": -100.0, "2023FY": -120.0},
        "cash_and_equivalents.ending": {"2022FY": 200.0, "2023FY": 250.0},
        "eps.basic":                 {"2022FY": 4000.0, "2023FY": 6000.0},
        "current_assets.ending":     {"2022FY":  900.0, "2023FY": 1000.0},
        "current_liabilities.ending":{"2022FY":  450.0, "2023FY":  500.0},
        "inventory.ending":          {"2022FY":  300.0, "2023FY":  350.0},
    }


class TestComputeRatios:
    def test_gross_margin(self):
        ratios = compute_ratios(_base_table())
        assert "gross_margin" in ratios
        assert ratios["gross_margin"]["2023FY"] == pytest.approx(0.4, abs=1e-5)

    def test_net_margin(self):
        ratios = compute_ratios(_base_table())
        assert "net_margin" in ratios
        assert ratios["net_margin"]["2023FY"] == pytest.approx(0.12, abs=1e-5)

    def test_roe(self):
        ratios = compute_ratios(_base_table())
        assert "roe" in ratios
        assert ratios["roe"]["2023FY"] == pytest.approx(600.0 / 2400.0, abs=1e-5)

    def test_roa(self):
        ratios = compute_ratios(_base_table())
        assert "roa" in ratios
        assert ratios["roa"]["2023FY"] == pytest.approx(600.0 / 3600.0, abs=1e-5)

    def test_debt_to_equity(self):
        ratios = compute_ratios(_base_table())
        assert "debt_to_equity" in ratios
        # 500 / 2400
        assert ratios["debt_to_equity"]["2023FY"] == pytest.approx(500.0 / 2400.0, abs=1e-5)

    def test_current_ratio(self):
        ratios = compute_ratios(_base_table())
        assert "current_ratio" in ratios
        assert ratios["current_ratio"]["2023FY"] == pytest.approx(1000.0 / 500.0, abs=1e-5)

    def test_quick_ratio(self):
        ratios = compute_ratios(_base_table())
        assert "quick_ratio" in ratios
        # (1000 - 350) / 500
        assert ratios["quick_ratio"]["2023FY"] == pytest.approx(650.0 / 500.0, abs=1e-5)

    def test_ocf_margin(self):
        ratios = compute_ratios(_base_table())
        assert "ocf_margin" in ratios
        assert ratios["ocf_margin"]["2023FY"] == pytest.approx(700.0 / 5000.0, abs=1e-5)

    def test_revenue_growth_computed(self):
        ratios = compute_ratios(_base_table())
        assert "revenue_growth" in ratios
        # Growth from 2022 to 2023 = (5000 - 4000) / 4000 = 0.25
        assert ratios["revenue_growth"]["2023FY"] == pytest.approx(0.25, abs=1e-5)

    def test_no_growth_for_single_period(self):
        table = {"revenue.net": {"2023FY": 5000.0}}
        ratios = compute_ratios(table)
        assert "revenue_growth" not in ratios

    def test_empty_table(self):
        ratios = compute_ratios({})
        assert ratios == {}

    def test_missing_metric_produces_no_ratio(self):
        table = {"gross_profit.total": {"2023FY": 2000.0}}  # no revenue
        ratios = compute_ratios(table)
        assert "gross_margin" not in ratios

    def test_zero_denominator_produces_no_ratio(self):
        table = {
            "revenue.net":        {"2023FY": 0.0},
            "gross_profit.total": {"2023FY": 0.0},
        }
        ratios = compute_ratios(table)
        assert "gross_margin" not in ratios

    def test_non_fy_periods_excluded_from_ratios(self):
        table = {
            "revenue.net":        {"2023FY": 5000.0, "2023Q1": 1200.0},
            "gross_profit.total": {"2023FY": 2000.0, "2023Q1":  480.0},
        }
        ratios = compute_ratios(table)
        assert "gross_margin" in ratios
        assert "2023FY" in ratios["gross_margin"]
        assert "2023Q1" not in ratios.get("gross_margin", {})

    def test_ebitda_margin(self):
        ratios = compute_ratios(_base_table())
        assert "ebitda_margin" in ratios
        assert ratios["ebitda_margin"]["2023FY"] == pytest.approx(1000.0 / 5000.0, abs=1e-5)


class TestRatioTableForDisplay:
    def _ratios(self):
        return {
            "gross_margin":   {"2023FY": 0.40},
            "net_margin":     {"2023FY": 0.12},
            "current_ratio":  {"2023FY": 2.0},
            "debt_to_equity": {"2023FY": 0.2083},
        }

    def test_percentage_formatting(self):
        display = ratio_table_for_display(self._ratios(), ["2023FY"])
        assert display["gross_margin"]["2023FY"] == "40.0%"
        assert display["net_margin"]["2023FY"] == "12.0%"

    def test_multiplier_formatting(self):
        display = ratio_table_for_display(self._ratios(), ["2023FY"])
        assert display["current_ratio"]["2023FY"] == "2.00x"

    def test_missing_period_shows_dash(self):
        display = ratio_table_for_display(self._ratios(), ["2022FY", "2023FY"])
        assert display["gross_margin"]["2022FY"] == "—"

    def test_empty_ratios(self):
        display = ratio_table_for_display({}, ["2023FY"])
        assert display == {}
