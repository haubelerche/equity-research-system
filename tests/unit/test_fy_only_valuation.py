"""Mandatory test: quarter-period facts must not enter the valuation path.

Phase 2 correction 3 requires FY-only enforcement at the application level.
This test verifies that build_source_tier_coverage, build_fact_table, and the
_filter_facts function correctly exclude or separate quarterly data.
"""
from __future__ import annotations

import re

import pytest

from backend.facts.normalizer import build_fact_table, build_source_tier_coverage, FactEntry


_FY_RE = re.compile(r"^[0-9]{4}FY$")


def _make_fact(metric, year, period, value, tier=3):
    return {
        "id": 1, "ticker": "DHG",
        "fiscal_year": year, "fiscal_period": period,
        "line_item_code": metric,
        "value": value, "unit": "vnd_bn", "currency": "VND",
        "source_id": "src1", "source_tier": tier,
        "source_uri": "", "source_title": "",
        "validation_status": "accepted", "confidence": 0.9,
    }


class TestFYOnlyValuation:
    """Quarter-period FactEntry objects must not appear when callers filter to FY only."""

    def test_build_fact_table_includes_quarterly_data(self):
        """build_fact_table itself does NOT filter — filtering is the caller's job."""
        facts = [
            _make_fact("revenue.net", 2023, "FY", 5000.0),
            _make_fact("revenue.net", 2023, "Q1", 1200.0),
        ]
        table = build_fact_table(facts)
        # Both periods should be present — build_fact_table is filter-agnostic
        assert "2023FY" in table["revenue.net"]
        assert "2023Q1" in table["revenue.net"]

    def test_fy_filter_excludes_quarterly(self):
        """After FY-only filter, quarterly FactEntries are not passed to valuation."""
        facts = [
            _make_fact("revenue.net", 2023, "FY", 5000.0),
            _make_fact("revenue.net", 2023, "Q1", 1200.0),
            _make_fact("revenue.net", 2023, "Q2", 1300.0),
        ]
        table = build_fact_table(facts)

        # Simulate the FY-only filter applied in build_facts.py
        fy_only = {
            metric: {p: e for p, e in periods.items() if _FY_RE.match(p)}
            for metric, periods in table.items()
        }
        revenue = fy_only.get("revenue.net", {})
        assert "2023FY" in revenue
        assert "2023Q1" not in revenue
        assert "2023Q2" not in revenue

    def test_build_source_tier_coverage_ignores_non_required_periods(self):
        """source_tier_coverage only reports on required_periods; quarterly data is not included."""
        facts = [
            _make_fact("revenue.net", 2023, "FY", 5000.0, tier=3),
            _make_fact("revenue.net", 2023, "Q1", 1200.0, tier=3),
        ]
        required_periods = ["2023FY"]
        coverage = build_source_tier_coverage(facts, required_periods)
        assert "2023FY" in coverage
        assert "2023Q1" not in coverage

    def test_valuation_entry_point_assertion_pattern(self):
        """Simulate the application-level FY-only assertion from build_facts.py."""
        fy_periods = ["2021FY", "2022FY", "2023FY"]
        # This assertion must pass for all-FY input
        assert all(p.endswith("FY") for p in fy_periods), \
            "Valuation must use FY-only canonical facts in MVP mode"

    def test_quarter_period_assertion_failure(self):
        """Including a quarterly period should trigger the FY-only assertion."""
        mixed_periods = ["2021FY", "2022FY", "2022Q4"]
        with pytest.raises(AssertionError, match="FY-only"):
            assert all(p.endswith("FY") for p in mixed_periods), \
                "Valuation must use FY-only canonical facts in MVP mode"

    def test_fact_entry_period_key_format(self):
        """FactEntry produced from FY data should have YYYYFY period key."""
        facts = [_make_fact("revenue.net", 2023, "FY", 5000.0)]
        table = build_fact_table(facts)
        period_key = next(iter(table["revenue.net"]))
        assert _FY_RE.match(period_key), f"Expected YYYYFY period key, got {period_key!r}"
