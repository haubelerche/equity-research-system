"""Tests for backend/analytics/capex.py — CAPEX sign validation and BS-based computation.

Covers:
- Normal balance-sheet CAPEX derivation
- Negative CAPEX input (CFS convention) auto-converted to positive
- Zero net disposal year
- Revenue intensity warning threshold
- D&A coverage warning
- Multi-year series validation including 3-consecutive-underspend detection
"""
from __future__ import annotations

import pytest

from backend.analytics.capex import (
    CapexAuditResult,
    audit_capex_entry,
    compute_capex_from_balance_sheet,
    validate_capex_series,
)


# ---------------------------------------------------------------------------
# compute_capex_from_balance_sheet
# ---------------------------------------------------------------------------


class TestComputeCapexFromBalanceSheet:
    def test_normal_case_tangible_only(self):
        """Pure tangible PP&E increase with no disposals."""
        result = compute_capex_from_balance_sheet(
            gross_tangible_ppe_current=500.0,
            gross_tangible_ppe_prior=440.0,
            year_label="2025FY",
        )
        assert isinstance(result, CapexAuditResult)
        assert result.capex_positive == pytest.approx(60.0)
        assert result.source == "balance_sheet"
        assert result.warnings == []

    def test_includes_intangible_and_wip(self):
        """CAPEX should sum tangible + intangible + WIP deltas."""
        result = compute_capex_from_balance_sheet(
            gross_tangible_ppe_current=500.0,
            gross_tangible_ppe_prior=450.0,
            intangible_gross_current=30.0,
            intangible_gross_prior=20.0,
            wip_current=15.0,
            wip_prior=10.0,
            year_label="2025FY",
        )
        # 50 (tangible) + 10 (intangible) + 5 (wip) = 65
        assert result.capex_positive == pytest.approx(65.0)
        assert result.source == "balance_sheet"

    def test_disposals_add_back_to_capex(self):
        """Gross disposals should be added back to recover gross additions."""
        result = compute_capex_from_balance_sheet(
            gross_tangible_ppe_current=490.0,
            gross_tangible_ppe_prior=480.0,  # net increase = 10 (after disposal of 20)
            disposed_gross_value=20.0,
            year_label="2025FY",
        )
        # delta_tangible=10, disposed=20 → gross additions = 30
        assert result.capex_positive == pytest.approx(30.0)
        assert result.source == "balance_sheet"

    def test_zero_net_disposal_year(self):
        """When disposals exceed gross additions, result is zero (net disposal year)."""
        result = compute_capex_from_balance_sheet(
            gross_tangible_ppe_current=430.0,
            gross_tangible_ppe_prior=480.0,  # net decrease = -50
            disposed_gross_value=10.0,
            year_label="2025FY",
        )
        # delta = -50, disposed = 10 → raw = -40
        assert result.capex_positive == 0.0
        assert result.source == "zero_net_disposal"
        assert len(result.warnings) == 1
        assert "zero" in result.warnings[0].lower() or "disposal" in result.warnings[0].lower()

    def test_disposed_gross_value_negative_sign_handled(self):
        """If caller passes disposed_gross_value as negative, abs() should handle it."""
        result = compute_capex_from_balance_sheet(
            gross_tangible_ppe_current=500.0,
            gross_tangible_ppe_prior=460.0,
            disposed_gross_value=-15.0,  # negative passed in error
            year_label="2025FY",
        )
        # delta=40, disposed abs=15 → 55
        assert result.capex_positive == pytest.approx(55.0)
        assert result.source == "balance_sheet"

    def test_no_change_zero_capex(self):
        """Completely flat balance sheet with no disposals → zero CAPEX."""
        result = compute_capex_from_balance_sheet(
            gross_tangible_ppe_current=400.0,
            gross_tangible_ppe_prior=400.0,
            year_label="2025FY",
        )
        assert result.capex_positive == 0.0
        assert result.source == "balance_sheet"
        assert result.warnings == []

    def test_year_label_propagated(self):
        result = compute_capex_from_balance_sheet(
            gross_tangible_ppe_current=100.0,
            gross_tangible_ppe_prior=80.0,
            year_label="2024FY",
        )
        assert result.year_label == "2024FY"

    def test_to_dict_structure(self):
        result = compute_capex_from_balance_sheet(
            gross_tangible_ppe_current=100.0,
            gross_tangible_ppe_prior=80.0,
            year_label="2024FY",
        )
        d = result.to_dict()
        assert set(d.keys()) == {"year_label", "capex_positive", "source", "warnings"}
        assert d["capex_positive"] == pytest.approx(20.0)


# ---------------------------------------------------------------------------
# audit_capex_entry
# ---------------------------------------------------------------------------


class TestAuditCapexEntry:
    def test_positive_capex_no_warnings(self):
        result = audit_capex_entry(capex=50.0, year_label="2025FY")
        assert result["capex_positive"] == pytest.approx(50.0)
        assert result["warnings"] == []

    def test_negative_capex_converted_and_warned(self):
        """Negative CFS-convention CAPEX should be converted to positive with warning."""
        result = audit_capex_entry(capex=-50.0, year_label="2025FY")
        assert result["capex_positive"] == pytest.approx(50.0)
        assert len(result["warnings"]) == 1
        assert "abs()" in result["warnings"][0] or "converted" in result["warnings"][0].lower()

    def test_zero_capex_no_warnings(self):
        result = audit_capex_entry(capex=0.0, year_label="2025FY")
        assert result["capex_positive"] == 0.0
        assert result["warnings"] == []

    def test_capex_revenue_intensity_warning(self):
        """CAPEX/Revenue > 30% should emit intensity warning."""
        result = audit_capex_entry(capex=35.0, year_label="2025FY", revenue=100.0)
        assert any("30%" in w or "exceeds" in w.lower() for w in result["warnings"])

    def test_capex_revenue_below_threshold_no_warning(self):
        result = audit_capex_entry(capex=20.0, year_label="2025FY", revenue=100.0)
        assert not any("30%" in w for w in result["warnings"])

    def test_capex_revenue_exactly_at_threshold_no_warning(self):
        """Exactly 30% should not warn (boundary: > not >=)."""
        result = audit_capex_entry(capex=30.0, year_label="2025FY", revenue=100.0)
        intensity_warnings = [w for w in result["warnings"] if "30%" in w or "Revenue" in w]
        assert intensity_warnings == []

    def test_capex_below_half_depreciation_warns(self):
        """CAPEX < 50% of D&A should warn about asset deterioration."""
        result = audit_capex_entry(capex=10.0, year_label="2025FY", depreciation=30.0)
        assert any("50%" in w or "deteriorat" in w.lower() for w in result["warnings"])

    def test_capex_above_half_depreciation_no_warn(self):
        result = audit_capex_entry(capex=20.0, year_label="2025FY", depreciation=30.0)
        depreciation_warnings = [w for w in result["warnings"] if "D&A" in w or "depreciat" in w.lower()]
        assert depreciation_warnings == []

    def test_both_warnings_can_trigger(self):
        """Both intensity and D&A coverage warnings can fire simultaneously."""
        result = audit_capex_entry(
            capex=40.0,
            year_label="2025FY",
            revenue=100.0,   # 40% → intensity warning
            depreciation=100.0,  # 40 < 50 → D&A warning
        )
        assert len(result["warnings"]) == 2

    def test_no_revenue_no_intensity_check(self):
        """Without revenue, no intensity warning should be emitted."""
        result = audit_capex_entry(capex=999.0, year_label="2025FY", revenue=None)
        assert not any("Revenue" in w for w in result["warnings"])

    def test_negative_capex_with_revenue_warning(self):
        """Negative CAPEX converted to positive should still trigger intensity check."""
        result = audit_capex_entry(capex=-40.0, year_label="2025FY", revenue=100.0)
        assert result["capex_positive"] == pytest.approx(40.0)
        # Should have conversion warning + intensity warning
        assert len(result["warnings"]) == 2


# ---------------------------------------------------------------------------
# validate_capex_series
# ---------------------------------------------------------------------------


class TestValidateCapexSeries:
    def test_empty_series_returns_empty(self):
        assert validate_capex_series([]) == []

    def test_normal_series_no_warnings(self):
        entries = [
            {"year": "2023FY", "capex": 50.0, "revenue": 500.0, "depreciation": 40.0},
            {"year": "2024FY", "capex": 55.0, "revenue": 520.0, "depreciation": 42.0},
            {"year": "2025FY", "capex": 60.0, "revenue": 550.0, "depreciation": 45.0},
        ]
        results = validate_capex_series(entries)
        assert len(results) == 3
        for r in results:
            assert r["warnings"] == []

    def test_negative_capex_in_series_converted(self):
        entries = [
            {"year": "2025FY", "capex": -50.0, "revenue": None, "depreciation": None},
        ]
        results = validate_capex_series(entries)
        assert results[0]["capex_positive"] == pytest.approx(50.0)
        assert len(results[0]["warnings"]) == 1

    def test_series_level_three_consecutive_underspend(self):
        """3 consecutive years with CAPEX < 50% D&A should produce series warning."""
        entries = [
            {"year": "2023FY", "capex": 10.0, "revenue": None, "depreciation": 40.0},
            {"year": "2024FY", "capex": 10.0, "revenue": None, "depreciation": 40.0},
            {"year": "2025FY", "capex": 10.0, "revenue": None, "depreciation": 40.0},
        ]
        results = validate_capex_series(entries)
        # Series warning goes on last entry
        series_w = results[-1].get("series_warnings", [])
        assert len(series_w) >= 1
        assert any("3+" in w or "consecutive" in w.lower() for w in series_w)

    def test_series_level_two_consecutive_no_trigger(self):
        """Only 2 consecutive years of underspend should not trigger series warning."""
        entries = [
            {"year": "2023FY", "capex": 10.0, "revenue": None, "depreciation": 40.0},
            {"year": "2024FY", "capex": 10.0, "revenue": None, "depreciation": 40.0},
            {"year": "2025FY", "capex": 30.0, "revenue": None, "depreciation": 40.0},
        ]
        results = validate_capex_series(entries)
        series_w = results[-1].get("series_warnings", [])
        assert series_w == []

    def test_single_entry_has_series_warnings_key(self):
        """Even a single entry should have the series_warnings key on the last element."""
        entries = [{"year": "2025FY", "capex": 50.0, "revenue": None, "depreciation": None}]
        results = validate_capex_series(entries)
        assert "series_warnings" in results[-1]

    def test_intensity_warning_in_series(self):
        entries = [
            {"year": "2025FY", "capex": 40.0, "revenue": 100.0, "depreciation": None},
        ]
        results = validate_capex_series(entries)
        assert any("30%" in w or "exceeds" in w.lower() for w in results[0]["warnings"])
