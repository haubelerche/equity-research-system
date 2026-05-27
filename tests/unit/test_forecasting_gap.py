"""Unit tests for the other_items_to_revenue (PBT gap) fix in forecasting.py.

Covers:
  - other_items driver computed correctly from historical PBT gap
  - forecast PBT includes other_items (not just EBIT + interest)
  - warning added when historical gap is non-zero
  - other_items_to_rev defaults to 0.0 when historical data is missing
"""
from __future__ import annotations

import statistics

import pytest

from backend.analytics.forecasting import ForecastArtifact, ForecastYear, run_forecast
from backend.facts.normalizer import FactTable


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dhg_like_fact_table() -> FactTable:
    """Fact table modelled on DHG 2022–2025 where PBT < EBIT + interest.

    Values (tỷ VND, approximate):
      2022FY: revenue=4200, gross_profit=1500, sga=-156, interest=-10, PBT=1099.6
      2023FY: revenue=4500, gross_profit=1600, sga=-235, interest=-10, PBT=1159.2
      2024FY: revenue=4800, gross_profit=1500, sga=-267, interest=-12, PBT=904.5
      2025FY: revenue=4900, gross_profit=1600, sga=-251, interest=-15, PBT=986.6

    EBIT_model = gross_profit + sga
    naive_pbt  = EBIT_model + interest
    other_items = PBT - naive_pbt   → consistently negative
    """
    return {
        "revenue.net": {
            "2022FY": 4200.0,
            "2023FY": 4500.0,
            "2024FY": 4800.0,
            "2025FY": 4900.0,
        },
        "gross_profit.total": {
            "2022FY": 1500.0,
            "2023FY": 1600.0,
            "2024FY": 1500.0,
            "2025FY": 1600.0,
        },
        "sga.total": {
            "2022FY": -156.0,
            "2023FY": -235.0,
            "2024FY": -267.0,
            "2025FY": -251.0,
        },
        "interest_expense.total": {
            "2022FY": -10.0,
            "2023FY": -10.0,
            "2024FY": -12.0,
            "2025FY": -15.0,
        },
        "profit_before_tax.total": {
            "2022FY": 1099.6,
            "2023FY": 1159.2,
            "2024FY": 904.5,
            "2025FY": 986.6,
        },
        "tax_expense.total": {
            "2022FY": -219.9,
            "2023FY": -231.8,
            "2024FY": -180.9,
            "2025FY": -197.3,
        },
    }


def _no_gap_fact_table() -> FactTable:
    """Fact table where PBT exactly equals EBIT + interest (gap = 0)."""
    return {
        "revenue.net": {"2023FY": 3000.0, "2024FY": 3200.0},
        "gross_profit.total": {"2023FY": 900.0, "2024FY": 960.0},
        "sga.total": {"2023FY": -150.0, "2024FY": -160.0},
        "interest_expense.total": {"2023FY": -30.0, "2024FY": -32.0},
        # PBT = gross_profit + sga + interest  (exact match → gap = 0)
        "profit_before_tax.total": {
            "2023FY": 900.0 - 150.0 - 30.0,   # = 720.0
            "2024FY": 960.0 - 160.0 - 32.0,   # = 768.0
        },
        "tax_expense.total": {"2023FY": -144.0, "2024FY": -153.6},
    }


def _missing_pbt_fact_table() -> FactTable:
    """Fact table that lacks profit_before_tax — other_items cannot be computed."""
    return {
        "revenue.net": {"2023FY": 3000.0, "2024FY": 3200.0},
        "gross_profit.total": {"2023FY": 900.0, "2024FY": 960.0},
        "sga.total": {"2023FY": -150.0, "2024FY": -160.0},
        "interest_expense.total": {"2023FY": -30.0, "2024FY": -32.0},
        # profit_before_tax.total intentionally omitted
    }


# ---------------------------------------------------------------------------
# Test 1: other_items driver computed from historical PBT gap
# ---------------------------------------------------------------------------

class TestOtherItemsDriverComputedFromHistoricalGap:
    """Verify that other_items_to_rev equals the median of (gap / revenue)."""

    def test_driver_value_matches_manual_median(self):
        table = _dhg_like_fact_table()
        artifact = run_forecast("DHG", table, n_years=1)

        # Manually compute expected other_items ratios for each period
        periods = ["2022FY", "2023FY", "2024FY", "2025FY"]
        ratios = []
        for p in periods:
            gp = table["gross_profit.total"][p]
            sga = table["sga.total"][p]
            ie = table["interest_expense.total"][p]
            pbt = table["profit_before_tax.total"][p]
            rev = table["revenue.net"][p]
            ebit_model = gp + sga
            other = pbt - (ebit_model + ie)
            ratios.append(other / rev)

        expected_driver = round(statistics.median(ratios), 4)
        actual_driver = artifact.drivers["other_items_to_revenue"]["value"]

        assert actual_driver == expected_driver, (
            f"other_items_to_revenue driver mismatch: "
            f"expected {expected_driver}, got {actual_driver}"
        )

    def test_driver_is_negative_for_dhg_like_data(self):
        """For DHG-like data the gap is consistently negative — driver must be < 0."""
        table = _dhg_like_fact_table()
        artifact = run_forecast("DHG", table, n_years=1)
        driver_value = artifact.drivers["other_items_to_revenue"]["value"]
        assert driver_value < 0, (
            f"Expected negative other_items_to_revenue for DHG-like data, got {driver_value}"
        )

    def test_driver_method_is_historical_median(self):
        table = _dhg_like_fact_table()
        artifact = run_forecast("DHG", table, n_years=1)
        assert artifact.drivers["other_items_to_revenue"]["method"] == "historical_median"


# ---------------------------------------------------------------------------
# Test 2: forecast PBT includes other_items (not just EBIT + interest)
# ---------------------------------------------------------------------------

class TestForecastPBTIncludesOtherItems:
    """Verify that forecast PBT ≠ EBIT + interest_expense (other_items is applied)."""

    def test_pbt_not_equal_to_ebit_plus_interest_when_gap_exists(self):
        table = _dhg_like_fact_table()
        artifact = run_forecast("DHG", table, n_years=3)

        for fy in artifact.forecast_years:
            naive_pbt = fy.ebit + fy.interest_expense  # without other_items
            assert abs(fy.profit_before_tax - naive_pbt) > 1.0, (
                f"Year {fy.year}: PBT ({fy.profit_before_tax:.1f}) should differ from "
                f"naive EBIT+interest ({naive_pbt:.1f}) when other_items gap exists."
            )

    def test_pbt_equals_ebit_plus_interest_plus_other_items(self):
        """Accounting identity: PBT = EBIT + interest_expense + other_items."""
        table = _dhg_like_fact_table()
        artifact = run_forecast("DHG", table, n_years=3)

        for fy in artifact.forecast_years:
            reconstructed = fy.ebit + fy.interest_expense + fy.other_items
            assert abs(fy.profit_before_tax - reconstructed) < 0.01, (
                f"Year {fy.year}: PBT identity broken. "
                f"PBT={fy.profit_before_tax:.3f}, "
                f"EBIT+IE+OI={reconstructed:.3f}"
            )

    def test_other_items_field_is_populated(self):
        table = _dhg_like_fact_table()
        artifact = run_forecast("DHG", table, n_years=3)

        for fy in artifact.forecast_years:
            assert fy.other_items is not None, (
                f"Year {fy.year}: other_items field should not be None"
            )

    def test_to_dict_includes_other_items(self):
        table = _dhg_like_fact_table()
        artifact = run_forecast("DHG", table, n_years=2)
        d = artifact.to_dict()

        for year_dict in d["forecast"]:
            assert "other_items" in year_dict, (
                f"to_dict() missing 'other_items' key for year {year_dict.get('year')}"
            )
            assert year_dict["other_items"] is not None


# ---------------------------------------------------------------------------
# Test 3: warning added when historical gap exists
# ---------------------------------------------------------------------------

class TestOtherItemsWarningAddedWhenGapExists:
    """Verify a descriptive warning appears in ForecastArtifact.warnings."""

    def test_warning_present_when_gap_nonzero(self):
        table = _dhg_like_fact_table()
        artifact = run_forecast("DHG", table, n_years=1)

        matching = [w for w in artifact.warnings if "Non-operating items" in w]
        assert matching, (
            f"Expected a 'Non-operating items' warning, got: {artifact.warnings}"
        )

    def test_warning_contains_percentage(self):
        table = _dhg_like_fact_table()
        artifact = run_forecast("DHG", table, n_years=1)

        matching = [w for w in artifact.warnings if "Non-operating items" in w]
        assert matching, "No non-operating items warning found"
        warning_text = matching[0]
        # Should contain a % figure for the median ratio
        assert "%" in warning_text, f"Warning should contain '%' sign: {warning_text}"

    def test_warning_contains_range(self):
        """Warning should mention both min and max of individual year ratios."""
        table = _dhg_like_fact_table()
        artifact = run_forecast("DHG", table, n_years=1)

        matching = [w for w in artifact.warnings if "Non-operating items" in w]
        assert matching
        warning_text = matching[0]
        # Expect mention of range ("ranged from ... to ...")
        assert "ranged from" in warning_text, (
            f"Warning should mention range of values: {warning_text}"
        )

    def test_no_warning_when_gap_is_zero(self):
        """When PBT == EBIT + interest for all periods, no non-operating warning."""
        table = _no_gap_fact_table()
        artifact = run_forecast("TEST", table, n_years=1)

        matching = [w for w in artifact.warnings if "Non-operating items" in w]
        assert not matching, (
            f"Should be no non-operating items warning when gap is zero, got: {artifact.warnings}"
        )


# ---------------------------------------------------------------------------
# Test 4: other_items_to_rev = 0.0 when historical PBT data is missing
# ---------------------------------------------------------------------------

class TestOtherItemsZeroWhenNoHistoricalData:
    """When profit_before_tax is absent, other_items_to_rev must default to 0.0."""

    def test_driver_is_zero_when_pbt_missing(self):
        table = _missing_pbt_fact_table()
        artifact = run_forecast("NOPBT", table, n_years=1)

        driver_value = artifact.drivers["other_items_to_revenue"]["value"]
        assert driver_value == 0.0, (
            f"Expected other_items_to_revenue=0.0 when PBT missing, got {driver_value}"
        )

    def test_other_items_is_zero_in_forecast_when_driver_is_zero(self):
        table = _missing_pbt_fact_table()
        artifact = run_forecast("NOPBT", table, n_years=2)

        for fy in artifact.forecast_years:
            assert fy.other_items == 0.0 or fy.other_items is None or abs(fy.other_items) < 0.01, (
                f"Year {fy.year}: other_items should be ~0 when driver is 0, got {fy.other_items}"
            )

    def test_pbt_equals_ebit_plus_interest_when_driver_zero(self):
        """When other_items_to_rev=0, PBT should equal EBIT + interest."""
        table = _no_gap_fact_table()
        artifact = run_forecast("TEST", table, n_years=2)

        # other_items_to_rev should be 0 for this table
        driver_value = artifact.drivers["other_items_to_revenue"]["value"]
        assert driver_value == 0.0, f"Expected 0.0 driver for no-gap table, got {driver_value}"

        for fy in artifact.forecast_years:
            naive_pbt = fy.ebit + fy.interest_expense
            assert abs(fy.profit_before_tax - naive_pbt) < 0.01, (
                f"Year {fy.year}: PBT should equal EBIT+interest when other_items=0. "
                f"PBT={fy.profit_before_tax:.3f}, naive={naive_pbt:.3f}"
            )
