"""Mandatory test: build_fact_table() must return FactEntry objects, not bare floats.

This is the primary regression guard for Phase 2 of the Data Trust Layer.
If this test ever fails, it means source provenance has been stripped from
the pipeline at normalization — the most critical lineage gap identified in
the Phase 0 audit.
"""
from __future__ import annotations

import pytest
from backend.facts.normalizer import FactEntry, FactTable, build_fact_table, compute_derived


def _fact(metric: str, year: int, value: float, source_id: str = "s1", tier: int = 3) -> dict:
    return {
        "id": 1, "ticker": "DHG",
        "fiscal_year": year, "fiscal_period": "FY",
        "line_item_code": metric,
        "value": value, "unit": "vnd_bn", "currency": "VND",
        "source_id": source_id, "source_tier": tier,
        "source_uri": f"vnstock://test/{metric}",
        "source_title": "Test",
        "validation_status": "accepted", "confidence": 0.9,
    }


class TestFactTableIsNotFloat:
    """Gate: no bare floats may appear in the FactTable after normalization."""

    def test_build_fact_table_returns_fact_entries(self):
        facts = [_fact("revenue.net", 2023, 5000.0)]
        table = build_fact_table(facts)
        entry = table["revenue.net"]["2023FY"]
        assert isinstance(entry, FactEntry), (
            f"build_fact_table returned {type(entry).__name__!r}, expected FactEntry. "
            "Source provenance is being lost at normalization — Phase 2 regression."
        )

    def test_no_bare_float_in_any_cell(self):
        facts = [
            _fact("revenue.net", 2023, 5000.0),
            _fact("net_income.parent", 2023, 1000.0),
            _fact("total_assets.ending", 2023, 8000.0),
            _fact("equity.parent", 2023, 4000.0),
            _fact("operating_cash_flow.total", 2023, 1200.0),
            _fact("capex.total", 2023, -200.0),
        ]
        table = build_fact_table(facts)
        for metric, periods in table.items():
            for period, entry in periods.items():
                assert not isinstance(entry, (int, float)), (
                    f"Bare numeric found at table[{metric!r}][{period!r}] = {entry!r}. "
                    "Expected FactEntry."
                )
                assert isinstance(entry, FactEntry), (
                    f"table[{metric!r}][{period!r}] is {type(entry).__name__!r}, not FactEntry."
                )

    def test_compute_derived_returns_fact_entries(self):
        facts = [
            _fact("revenue.net", 2023, 5000.0),
            _fact("gross_profit.total", 2023, 2500.0),
            _fact("net_income.parent", 2023, 1000.0),
            _fact("operating_cash_flow.total", 2023, 1200.0),
            _fact("capex.total", 2023, -200.0),
            _fact("total_debt.ending", 2023, 800.0),
            _fact("equity.parent", 2023, 4000.0),
        ]
        table = build_fact_table(facts)
        full = compute_derived(table)
        for metric, periods in full.items():
            for period, entry in periods.items():
                assert isinstance(entry, FactEntry), (
                    f"compute_derived produced bare value at [{metric!r}][{period!r}]."
                )

    def test_derived_entries_explicitly_mark_no_source(self):
        facts = [
            _fact("revenue.net", 2023, 5000.0),
            _fact("gross_profit.total", 2023, 2500.0),
        ]
        full = compute_derived(build_fact_table(facts))
        gm = full.get("gross_margin", {}).get("2023FY")
        assert gm is not None, "gross_margin should be computed"
        assert gm.source_id is None, "Derived entry must have source_id=None"
        assert gm.source_tier is None, "Derived entry must have source_tier=None"
        assert gm.is_derived(), "is_derived() must return True for computed metrics"

    def test_source_entries_carry_provenance(self):
        facts = [_fact("revenue.net", 2023, 5000.0, source_id="audit_abc", tier=0)]
        table = build_fact_table(facts)
        entry = table["revenue.net"]["2023FY"]
        assert entry.source_id == "audit_abc"
        assert entry.source_tier == 0
        assert not entry.is_derived()
