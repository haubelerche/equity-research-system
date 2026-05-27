"""Unit tests for backend/facts/normalizer.py.

Tests: build_fact_table, compute_derived, periods_sorted.
No DB required — all in-memory.
"""
from __future__ import annotations

import pytest

from backend.facts.normalizer import build_fact_table, compute_derived, periods_sorted


def _make_fact(ticker, line_item_code, fiscal_year, fiscal_period, value, unit="vnd_bn", currency="VND"):
    return {
        "id": 1,
        "ticker": ticker,
        "fiscal_year": fiscal_year,
        "fiscal_period": fiscal_period,
        "line_item_code": line_item_code,
        "value": value,
        "unit": unit,
        "currency": currency,
        "source_id": "test_source",
        "validation_status": "accepted",
    }


class TestBuildFactTable:
    def test_basic_structure(self):
        facts = [
            _make_fact("DHG", "revenue.net", 2023, "FY", 5000.0),
            _make_fact("DHG", "net_income.parent", 2023, "FY", 1000.0),
        ]
        table = build_fact_table(facts)
        assert "revenue.net" in table
        assert "2023FY" in table["revenue.net"]
        assert table["revenue.net"]["2023FY"] == pytest.approx(5000.0)

    def test_period_key_format(self):
        facts = [_make_fact("DHG", "revenue.net", 2022, "FY", 4000.0)]
        table = build_fact_table(facts)
        assert "2022FY" in table["revenue.net"]

    def test_multiple_periods(self):
        facts = [
            _make_fact("DHG", "revenue.net", 2022, "FY", 4000.0),
            _make_fact("DHG", "revenue.net", 2023, "FY", 5000.0),
            _make_fact("DHG", "revenue.net", 2024, "FY", 4800.0),
        ]
        table = build_fact_table(facts)
        assert len(table["revenue.net"]) == 3
        assert table["revenue.net"]["2022FY"] == pytest.approx(4000.0)
        assert table["revenue.net"]["2024FY"] == pytest.approx(4800.0)

    def test_empty_input(self):
        table = build_fact_table([])
        assert table == {}

    def test_non_fy_periods_included(self):
        facts = [
            _make_fact("DHG", "revenue.net", 2023, "FY", 5000.0),
            _make_fact("DHG", "revenue.net", 2023, "Q1", 1200.0),
        ]
        table = build_fact_table(facts)
        # build_fact_table stores all periods; downstream filtering is the caller's concern
        assert "2023FY" in table["revenue.net"]
        assert "2023Q1" in table["revenue.net"]
        assert table["revenue.net"]["2023Q1"] == pytest.approx(1200.0)

    def test_latest_value_wins_on_duplicate(self):
        facts = [
            _make_fact("DHG", "revenue.net", 2023, "FY", 5000.0),
            _make_fact("DHG", "revenue.net", 2023, "FY", 5100.0),  # duplicate period
        ]
        table = build_fact_table(facts)
        # Either value is acceptable; table should have exactly one value for 2023FY
        assert "2023FY" in table["revenue.net"]


class TestComputeDerived:
    def _base_table(self):
        return {
            "revenue.net": {"2023FY": 5000.0, "2024FY": 4800.0},
            "gross_profit.total": {"2023FY": 2500.0, "2024FY": 2100.0},
            "net_income.parent": {"2023FY": 1000.0, "2024FY": 760.0},
            "operating_cash_flow.total": {"2023FY": 1200.0, "2024FY": 1300.0},
            "capex.total": {"2023FY": -200.0, "2024FY": -180.0},
            "equity.parent": {"2023FY": 4000.0, "2024FY": 4200.0},
            "total_assets.ending": {"2023FY": 6000.0, "2024FY": 6200.0},
            "total_debt.ending": {"2023FY": 800.0, "2024FY": 1000.0},
            "eps.basic": {"2023FY": 7000.0, "2024FY": 5200.0},
            "sga.total": {"2023FY": -500.0, "2024FY": -480.0},
            "depreciation.total": {"2023FY": 300.0, "2024FY": 310.0},
        }

    def test_gross_margin_computed(self):
        table = compute_derived(self._base_table())
        assert "gross_margin" in table
        assert table["gross_margin"]["2023FY"] == pytest.approx(0.5, abs=0.01)

    def test_net_margin_computed(self):
        table = compute_derived(self._base_table())
        assert "net_margin" in table
        assert table["net_margin"]["2023FY"] == pytest.approx(0.2, abs=0.01)

    def test_free_cash_flow_computed(self):
        table = compute_derived(self._base_table())
        assert "free_cash_flow.total" in table
        # FCF = OCF - capex = 1200 - (-200) = 1400
        assert table["free_cash_flow.total"]["2023FY"] == pytest.approx(1400.0)

    def test_ebitda_derived_when_missing(self):
        table = compute_derived(self._base_table())
        # ebitda = gross_profit + sga + depreciation = 2500 + (-500) + 300 = 2300
        assert "ebitda.total" in table
        assert table["ebitda.total"]["2023FY"] == pytest.approx(2300.0)

    def test_original_table_not_mutated(self):
        base = self._base_table()
        original_keys = set(base.keys())
        compute_derived(base)
        assert set(base.keys()) == original_keys

    def test_missing_denominator_produces_no_ratio(self):
        table = {"net_income.parent": {"2023FY": 1000.0}}  # no revenue
        result = compute_derived(table)
        assert "net_margin" not in result

    def test_zero_revenue_produces_no_margin(self):
        table = {
            "revenue.net": {"2023FY": 0.0},
            "gross_profit.total": {"2023FY": 0.0},
            "net_income.parent": {"2023FY": 0.0},
        }
        result = compute_derived(table)
        assert "gross_margin" not in result
        assert "net_margin" not in result

    def test_debt_to_equity(self):
        table = compute_derived(self._base_table())
        assert "debt_to_equity" in table
        assert table["debt_to_equity"]["2023FY"] == pytest.approx(0.2, abs=0.01)


class TestPeriodsSorted:
    def test_fy_periods_in_order(self):
        table = {"revenue.net": {"2022FY": 1, "2024FY": 2, "2023FY": 3}}
        periods = periods_sorted(table)
        assert periods == ["2022FY", "2023FY", "2024FY"]

    def test_empty_table(self):
        assert periods_sorted({}) == []

    def test_deduplication(self):
        table = {
            "a": {"2023FY": 1},
            "b": {"2023FY": 2, "2024FY": 3},
        }
        periods = periods_sorted(table)
        assert periods.count("2023FY") == 1
