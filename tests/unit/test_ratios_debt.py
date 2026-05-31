"""Tests for debt_to_equity and roce correctness in ratios.py."""
from __future__ import annotations

import pytest

from backend.analytics.ratios import compute_ratios


def _table_with_liabilities_only() -> dict:
    return {
        "revenue.net":              {"2024FY": 4000.0},
        "gross_profit.total":       {"2024FY": 1600.0},
        "net_income.parent":        {"2024FY": 500.0},
        "equity.parent":            {"2024FY": 2000.0},
        "total_assets.ending":      {"2024FY": 4500.0},
        "total_liabilities.ending": {"2024FY": 2500.0},
        # total_debt.ending intentionally absent
    }


def _table_with_debt() -> dict:
    return {
        "revenue.net":              {"2024FY": 4000.0},
        "gross_profit.total":       {"2024FY": 1600.0},
        "net_income.parent":        {"2024FY": 500.0},
        "equity.parent":            {"2024FY": 2000.0},
        "total_assets.ending":      {"2024FY": 4500.0},
        "total_liabilities.ending": {"2024FY": 2500.0},
        "total_debt.ending":        {"2024FY": 300.0},
    }


class TestDebtToEquity:
    def test_none_when_total_debt_missing(self):
        ratios = compute_ratios(_table_with_liabilities_only())
        de = ratios.get("debt_to_equity", {}).get("2024FY")
        assert de is None

    def test_uses_total_debt_when_available(self):
        ratios = compute_ratios(_table_with_debt())
        de = ratios["debt_to_equity"]["2024FY"]
        assert de == pytest.approx(300 / 2000, abs=0.001)

    def test_roce_uses_debt_not_liabilities(self):
        ratios = compute_ratios(_table_with_debt())
        # roce_base = equity + total_debt = 2000 + 300 = 2300
        roce = ratios.get("roce", {}).get("2024FY")
        assert roce is not None
        assert roce == pytest.approx(500 / 2300, abs=0.001)

    def test_roce_without_debt_uses_equity_only(self):
        ratios = compute_ratios(_table_with_liabilities_only())
        # roce_base = equity only = 2000 (no interest-bearing debt)
        roce = ratios.get("roce", {}).get("2024FY")
        assert roce == pytest.approx(500 / 2000, abs=0.001)
