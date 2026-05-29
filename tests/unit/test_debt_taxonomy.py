"""Tests for interest_bearing_debt() alias resolution in debt_schedule.py."""
from __future__ import annotations

import pytest

from backend.analytics.debt_schedule import interest_bearing_debt


class TestInterestBearingDebtAliases:
    def test_returns_total_debt_ending_first(self):
        ft = {"total_debt.ending": {"2024FY": 500.0}}
        assert interest_bearing_debt(ft, "2024FY") == 500.0

    def test_sums_short_long_borrowings(self):
        ft = {
            "short_term_borrowings.ending": {"2024FY": 200.0},
            "long_term_borrowings.ending": {"2024FY": 300.0},
        }
        assert interest_bearing_debt(ft, "2024FY") == pytest.approx(500.0)

    def test_alias_short_term_debt(self):
        ft = {
            "short_term_debt.ending": {"2024FY": 150.0},
            "long_term_debt.ending": {"2024FY": 350.0},
        }
        assert interest_bearing_debt(ft, "2024FY") == pytest.approx(500.0)

    def test_alias_short_only(self):
        ft = {"short_term_debt.ending": {"2024FY": 200.0}}
        assert interest_bearing_debt(ft, "2024FY") == pytest.approx(200.0)

    def test_alias_long_only(self):
        ft = {"long_term_debt.ending": {"2024FY": 300.0}}
        assert interest_bearing_debt(ft, "2024FY") == pytest.approx(300.0)

    def test_total_debt_takes_priority_over_alias(self):
        ft = {
            "total_debt.ending": {"2024FY": 500.0},
            "short_term_debt.ending": {"2024FY": 999.0},
        }
        assert interest_bearing_debt(ft, "2024FY") == 500.0

    def test_returns_none_when_truly_missing(self):
        ft = {"revenue.net": {"2024FY": 1000.0}}
        assert interest_bearing_debt(ft, "2024FY") is None

    def test_missing_period_returns_none(self):
        ft = {"total_debt.ending": {"2024FY": 500.0}}
        assert interest_bearing_debt(ft, "2023FY") is None
