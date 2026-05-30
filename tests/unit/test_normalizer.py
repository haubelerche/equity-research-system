"""Unit tests for backend/facts/normalizer.py.

Tests: FactEntry, build_fact_table, compute_derived, periods_sorted,
       build_source_conflict_report, build_source_tier_coverage.
No DB required — all in-memory.
"""
from __future__ import annotations

import pytest

from backend.facts.normalizer import (
    FactEntry,
    FactTable,
    build_fact_table,
    build_source_conflict_report,
    build_source_tier_coverage,
    compute_derived,
    periods_sorted,
)


def _make_fact(
    ticker, line_item_code, fiscal_year, fiscal_period, value,
    unit="vnd_bn", currency="VND", source_id="test_source",
    source_tier=3, confidence=0.85,
):
    return {
        "id": 1,
        "ticker": ticker,
        "fiscal_year": fiscal_year,
        "fiscal_period": fiscal_period,
        "line_item_code": line_item_code,
        "value": value,
        "unit": unit,
        "currency": currency,
        "source_id": source_id,
        "source_tier": source_tier,
        "source_uri": f"vnstock://test/{line_item_code}",
        "source_title": "Test Source",
        "validation_status": "accepted",
        "confidence": confidence,
    }


class TestFactEntry:
    def test_fact_entry_has_value(self):
        entry = FactEntry(value=1234.5)
        assert entry.value == pytest.approx(1234.5)

    def test_fact_entry_is_not_float(self):
        entry = FactEntry(value=1234.5, source_id="test", source_tier=3)
        assert not isinstance(entry, float)
        assert isinstance(entry, FactEntry)

    def test_fact_entry_stores_provenance(self):
        entry = FactEntry(
            value=5000.0,
            source_id="abc123",
            source_uri="vnstock://kbs/finance/income/DHG",
            source_tier=3,
            confidence=0.95,
        )
        assert entry.source_id == "abc123"
        assert entry.source_tier == 3
        assert entry.confidence == pytest.approx(0.95)

    def test_derived_entry_has_no_source(self):
        entry = FactEntry(value=0.25)
        assert entry.source_id is None
        assert entry.source_tier is None
        assert entry.is_derived()

    def test_sourced_entry_is_not_derived(self):
        entry = FactEntry(value=100.0, source_id="src1", source_tier=3)
        assert not entry.is_derived()


class TestBuildFactTable:
    def test_returns_fact_entry_objects_not_floats(self):
        """Mandatory test: build_fact_table must return FactEntry, not bare floats."""
        facts = [_make_fact("DHG", "revenue.net", 2023, "FY", 5000.0)]
        table = build_fact_table(facts)
        entry = table["revenue.net"]["2023FY"]
        assert isinstance(entry, FactEntry), "Expected FactEntry, got bare float or other type"
        assert not isinstance(entry, float)

    def test_entry_value_matches_fact(self):
        facts = [_make_fact("DHG", "revenue.net", 2023, "FY", 5000.0)]
        table = build_fact_table(facts)
        assert table["revenue.net"]["2023FY"].value == pytest.approx(5000.0)

    def test_entry_carries_source_tier(self):
        facts = [_make_fact("DHG", "revenue.net", 2023, "FY", 5000.0, source_tier=3)]
        table = build_fact_table(facts)
        assert table["revenue.net"]["2023FY"].source_tier == 3

    def test_basic_structure(self):
        facts = [
            _make_fact("DHG", "revenue.net", 2023, "FY", 5000.0),
            _make_fact("DHG", "net_income.parent", 2023, "FY", 1000.0),
        ]
        table = build_fact_table(facts)
        assert "revenue.net" in table
        assert "2023FY" in table["revenue.net"]

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
        assert table["revenue.net"]["2022FY"].value == pytest.approx(4000.0)
        assert table["revenue.net"]["2024FY"].value == pytest.approx(4800.0)

    def test_empty_input(self):
        assert build_fact_table([]) == {}

    def test_tier0_beats_tier3_on_same_period(self):
        """Lower source_tier wins over higher tier for the same (metric, period)."""
        facts = [
            _make_fact("DHG", "revenue.net", 2023, "FY", 5000.0, source_id="api_src", source_tier=3),
            _make_fact("DHG", "revenue.net", 2023, "FY", 5050.0, source_id="audit_src", source_tier=0),
        ]
        table = build_fact_table(facts)
        entry = table["revenue.net"]["2023FY"]
        assert entry.source_id == "audit_src", "Tier 0 source should win over Tier 3"
        assert entry.value == pytest.approx(5050.0)

    def test_higher_confidence_wins_within_same_tier(self):
        facts = [
            _make_fact("DHG", "revenue.net", 2023, "FY", 5000.0, source_id="src_low", source_tier=3, confidence=0.75),
            _make_fact("DHG", "revenue.net", 2023, "FY", 5100.0, source_id="src_high", source_tier=3, confidence=0.95),
        ]
        table = build_fact_table(facts)
        assert table["revenue.net"]["2023FY"].source_id == "src_high"

    def test_non_fy_periods_included(self):
        facts = [
            _make_fact("DHG", "revenue.net", 2023, "FY", 5000.0),
            _make_fact("DHG", "revenue.net", 2023, "Q1", 1200.0),
        ]
        table = build_fact_table(facts)
        assert "2023FY" in table["revenue.net"]
        assert "2023Q1" in table["revenue.net"]

    def test_source_id_preserved_in_entry(self):
        facts = [_make_fact("DHG", "revenue.net", 2023, "FY", 5000.0, source_id="my_source_001")]
        table = build_fact_table(facts)
        assert table["revenue.net"]["2023FY"].source_id == "my_source_001"


class TestComputeDerived:
    def _base_table(self) -> FactTable:
        def e(v):
            return FactEntry(value=v, source_id="test", source_tier=3)
        return {
            "revenue.net":              {"2023FY": e(5000.0), "2024FY": e(4800.0)},
            "gross_profit.total":       {"2023FY": e(2500.0), "2024FY": e(2100.0)},
            "net_income.parent":        {"2023FY": e(1000.0), "2024FY": e(760.0)},
            "operating_cash_flow.total":{"2023FY": e(1200.0), "2024FY": e(1300.0)},
            "capex.total":              {"2023FY": e(-200.0), "2024FY": e(-180.0)},
            "equity.parent":            {"2023FY": e(4000.0), "2024FY": e(4200.0)},
            "total_debt.ending":        {"2023FY": e(800.0),  "2024FY": e(1000.0)},
            "sga.total":                {"2023FY": e(-500.0), "2024FY": e(-480.0)},
            "depreciation.total":       {"2023FY": e(300.0),  "2024FY": e(310.0)},
        }

    def test_derived_entries_are_fact_entries(self):
        table = compute_derived(self._base_table())
        assert isinstance(table["gross_margin"]["2023FY"], FactEntry)

    def test_derived_entries_have_no_source(self):
        table = compute_derived(self._base_table())
        gm = table["gross_margin"]["2023FY"]
        assert gm.is_derived()
        assert gm.source_id is None
        assert gm.source_tier is None

    def test_gross_margin_computed(self):
        table = compute_derived(self._base_table())
        assert "gross_margin" in table
        assert table["gross_margin"]["2023FY"].value == pytest.approx(0.5, abs=0.01)

    def test_net_margin_computed(self):
        table = compute_derived(self._base_table())
        assert table["net_margin"]["2023FY"].value == pytest.approx(0.2, abs=0.01)

    def test_free_cash_flow_computed(self):
        table = compute_derived(self._base_table())
        assert table["free_cash_flow.total"]["2023FY"].value == pytest.approx(1000.0)

    def test_ebitda_derived_when_missing(self):
        table = compute_derived(self._base_table())
        # ebitda = gross_profit + sga + depreciation = 2500 + (-500) + 300 = 2300
        assert table["ebitda.total"]["2023FY"].value == pytest.approx(2300.0)

    def test_original_table_not_mutated(self):
        base = self._base_table()
        original_keys = set(base.keys())
        compute_derived(base)
        assert set(base.keys()) == original_keys

    def test_missing_denominator_produces_no_ratio(self):
        def e(v):
            return FactEntry(value=v, source_id="t", source_tier=3)
        table = {"net_income.parent": {"2023FY": e(1000.0)}}
        result = compute_derived(table)
        assert "net_margin" not in result

    def test_zero_revenue_produces_no_margin(self):
        def e(v):
            return FactEntry(value=v, source_id="t", source_tier=3)
        table = {
            "revenue.net":        {"2023FY": e(0.0)},
            "gross_profit.total": {"2023FY": e(0.0)},
            "net_income.parent":  {"2023FY": e(0.0)},
        }
        result = compute_derived(table)
        assert "gross_margin" not in result
        assert "net_margin" not in result

    def test_debt_to_equity(self):
        table = compute_derived(self._base_table())
        assert table["debt_to_equity"]["2023FY"].value == pytest.approx(0.2, abs=0.01)


class TestBuildSourceConflictReport:
    def test_no_conflict_single_source(self):
        facts = [_make_fact("DHG", "revenue.net", 2023, "FY", 5000.0, source_id="src1")]
        conflicts = build_source_conflict_report("DHG", facts)
        assert conflicts == []

    def test_no_conflict_small_variance(self):
        facts = [
            _make_fact("DHG", "revenue.net", 2023, "FY", 5000.0, source_id="src1"),
            _make_fact("DHG", "revenue.net", 2023, "FY", 5010.0, source_id="src2"),
        ]
        # 0.2% variance — below 2% threshold
        conflicts = build_source_conflict_report("DHG", facts)
        assert conflicts == []

    def test_conflict_detected_above_threshold(self):
        facts = [
            _make_fact("DHG", "revenue.net", 2023, "FY", 5000.0, source_id="src1", source_tier=3),
            _make_fact("DHG", "revenue.net", 2023, "FY", 5200.0, source_id="src2", source_tier=3),
        ]
        # variance = (5200-5000)/5200*100 ≈ 3.85% (above 2% threshold)
        conflicts = build_source_conflict_report("DHG", facts)
        assert len(conflicts) == 1
        assert conflicts[0].metric == "revenue.net"
        assert conflicts[0].variance_pct == pytest.approx(3.846, abs=0.1)
        assert not conflicts[0].requires_review  # < 10%

    def test_high_variance_requires_review(self):
        facts = [
            _make_fact("DHG", "revenue.net", 2023, "FY", 5000.0, source_id="src1"),
            _make_fact("DHG", "revenue.net", 2023, "FY", 5800.0, source_id="src2"),
        ]
        # 16% variance
        conflicts = build_source_conflict_report("DHG", facts)
        assert len(conflicts) == 1
        assert conflicts[0].requires_review

    def test_lower_tier_selected_as_winner(self):
        facts = [
            _make_fact("DHG", "revenue.net", 2023, "FY", 5000.0, source_id="api", source_tier=3),
            _make_fact("DHG", "revenue.net", 2023, "FY", 5500.0, source_id="audit", source_tier=0),
        ]
        conflicts = build_source_conflict_report("DHG", facts)
        assert conflicts[0].selected_source_id == "audit"


class TestBuildSourceTierCoverage:
    def test_tier3_only_period(self):
        facts = [_make_fact("DHG", "revenue.net", 2023, "FY", 5000.0, source_tier=3)]
        coverage = build_source_tier_coverage(facts, ["2023FY"])
        assert coverage["2023FY"]["has_tier01"] is False
        assert coverage["2023FY"]["min_tier"] == 3

    def test_tier0_period_flags_has_tier01(self):
        facts = [_make_fact("DHG", "revenue.net", 2023, "FY", 5000.0, source_tier=0)]
        coverage = build_source_tier_coverage(facts, ["2023FY"])
        assert coverage["2023FY"]["has_tier01"] is True
        assert coverage["2023FY"]["min_tier"] == 0

    def test_missing_period_returns_empty(self):
        coverage = build_source_tier_coverage([], ["2021FY", "2022FY"])
        assert coverage["2021FY"]["tiers_present"] == []
        assert coverage["2021FY"]["has_tier01"] is False


class TestPeriodsSorted:
    def test_fy_periods_in_order(self):
        def e(v):
            return FactEntry(value=v)
        table = {"revenue.net": {"2022FY": e(1), "2024FY": e(2), "2023FY": e(3)}}
        periods = periods_sorted(table)
        assert periods == ["2022FY", "2023FY", "2024FY"]

    def test_empty_table(self):
        assert periods_sorted({}) == []

    def test_deduplication(self):
        def e(v):
            return FactEntry(value=v)
        table = {
            "a": {"2023FY": e(1)},
            "b": {"2023FY": e(2), "2024FY": e(3)},
        }
        periods = periods_sorted(table)
        assert periods.count("2023FY") == 1
