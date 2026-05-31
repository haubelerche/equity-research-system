"""Unit tests for driver-based debt and dividend integration in forecasting.py.

Covers:
  - Interest expense = avg_debt × cost_of_debt (not revenue-based)
  - Zero-debt companies produce zero interest expense
  - Debt roll-forward: beginning_debt[year N+1] == ending_debt[year N]
  - Equity updated via dividend_schedule.retained_earnings_schedule() (Pass 2)
  - ForecastYear carries beginning_debt, ending_debt, net_borrowing, cost_of_debt
  - ForecastYear carries cash_dividend, payout_ratio, retained_earnings_addition
  - ForecastArtifact.debt_schedule is attached
  - No double-computation: payout logic lives only in dividend_schedule
  - to_dict() serialises all new fields
"""
from __future__ import annotations

import statistics

import pytest

from backend.analytics.forecasting import (
    ForecastAssumptions,
    ForecastArtifact,
    ForecastYear,
    run_forecast,
)
from backend.facts.normalizer import FactTable


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _debt_bearing_table() -> FactTable:
    """Company with interest-bearing debt and regular dividend payments.

    Interest-bearing debt (VND bn):
      2022FY: 500 → 2023FY: 520 → 2024FY: 550

    implied_cost_of_debt:
      2023FY: interest_expense=52 / beginning_debt=500 = 0.1040
      2024FY: interest_expense=55 / beginning_debt=520 = 0.1058
      median ≈ 0.1049

    Historical payout_ratio:
      2022FY: div=250/ni=840 = 0.2976
      2023FY: div=280/ni=920 = 0.3043
      2024FY: div=260/ni=720 = 0.3611
      median ≈ 0.3043
    """
    return {
        "revenue.net": {"2022FY": 4200.0, "2023FY": 4500.0, "2024FY": 4800.0},
        "gross_profit.total": {"2022FY": 1500.0, "2023FY": 1600.0, "2024FY": 1500.0},
        "sga.total": {"2022FY": -156.0, "2023FY": -235.0, "2024FY": -267.0},
        "interest_expense.total": {
            "2022FY": -50.0,
            "2023FY": -52.0,
            "2024FY": -55.0,
        },
        "total_debt.ending": {
            "2022FY": 500.0,
            "2023FY": 520.0,
            "2024FY": 550.0,
        },
        "total_assets.ending": {"2022FY": 2000.0, "2023FY": 2200.0, "2024FY": 2400.0},
        "equity.parent": {"2022FY": 1200.0, "2023FY": 1350.0, "2024FY": 1500.0},
        "profit_before_tax.total": {
            "2022FY": 1050.0,
            "2023FY": 1150.0,
            "2024FY": 900.0,
        },
        "tax_expense.total": {"2022FY": -210.0, "2023FY": -230.0, "2024FY": -180.0},
        "net_income.parent": {"2022FY": 840.0, "2023FY": 920.0, "2024FY": 720.0},
        "eps.basic": {"2022FY": 8400.0, "2023FY": 9200.0, "2024FY": 7200.0},
        "dividends_paid.total": {
            "2022FY": -250.0,
            "2023FY": -280.0,
            "2024FY": -260.0,
        },
    }


def _zero_debt_table() -> FactTable:
    """Company with no interest-bearing debt (zero_debt_policy case)."""
    return {
        "revenue.net": {"2023FY": 3000.0, "2024FY": 3200.0},
        "gross_profit.total": {"2023FY": 900.0, "2024FY": 960.0},
        "sga.total": {"2023FY": -150.0, "2024FY": -160.0},
        "interest_expense.total": {"2023FY": 0.0, "2024FY": 0.0},
        "total_debt.ending": {"2023FY": 0.0, "2024FY": 0.0},
        "total_assets.ending": {"2023FY": 1500.0, "2024FY": 1600.0},
        "equity.parent": {"2023FY": 1200.0, "2024FY": 1350.0},
        "profit_before_tax.total": {"2023FY": 720.0, "2024FY": 768.0},
        "tax_expense.total": {"2023FY": -144.0, "2024FY": -153.6},
        "net_income.parent": {"2023FY": 576.0, "2024FY": 614.4},
        "eps.basic": {"2023FY": 5760.0, "2024FY": 6144.0},
    }


def _no_debt_data_table() -> FactTable:
    """Company with no total_debt data at all — triggers fallback CoD."""
    return {
        "revenue.net": {"2023FY": 3000.0, "2024FY": 3200.0},
        "gross_profit.total": {"2023FY": 900.0, "2024FY": 960.0},
        "sga.total": {"2023FY": -150.0, "2024FY": -160.0},
        "interest_expense.total": {"2023FY": -30.0, "2024FY": -32.0},
        # No total_debt.ending → no implied_cost_of_debt derivable
        "profit_before_tax.total": {"2023FY": 720.0, "2024FY": 768.0},
        "tax_expense.total": {"2023FY": -144.0, "2024FY": -153.6},
        "net_income.parent": {"2023FY": 576.0, "2024FY": 614.4},
        "eps.basic": {"2023FY": 5760.0, "2024FY": 6144.0},
    }


# ---------------------------------------------------------------------------
# 1. Interest expense uses avg_debt × cost_of_debt
# ---------------------------------------------------------------------------

class TestInterestExpenseDriverBased:
    """Interest expense must equal -avg_debt × cost_of_debt for companies with debt."""

    def test_interest_expense_uses_avg_debt_not_revenue(self):
        """Interest expense must equal avg_debt × cost_of_debt, not revenue × ratio.

        Verifies the computation formula is debt-based by checking:
          interest_expense == -(beginning_debt + ending_debt) / 2 × cost_of_debt
        for every forecast year where debt data is present.
        """
        table = _debt_bearing_table()
        artifact = run_forecast("TST", table, n_years=3)
        cod = artifact.drivers["cost_of_debt"]["value"]

        for fy in artifact.forecast_years:
            if fy.beginning_debt is not None and fy.ending_debt is not None:
                expected = -((fy.beginning_debt + fy.ending_debt) / 2.0) * cod
                assert abs(fy.interest_expense - expected) < 0.5, (
                    f"Year {fy.year}: interest_expense {fy.interest_expense:.2f} "
                    f"≠ avg_debt × cod = {expected:.2f} — not using debt-based formula"
                )

    def test_cost_of_debt_driver_stored_in_artifact(self):
        table = _debt_bearing_table()
        artifact = run_forecast("TST", table, n_years=1)
        assert "cost_of_debt" in artifact.drivers
        assert artifact.drivers["cost_of_debt"]["value"] > 0

    def test_cost_of_debt_method_is_historical_implied(self):
        table = _debt_bearing_table()
        artifact = run_forecast("TST", table, n_years=1)
        assert artifact.drivers["cost_of_debt"]["method"] == "historical_implied_cod"

    def test_interest_expense_close_to_expected(self):
        """Verify interest_expense ≈ avg_debt × implied_cod for first forecast year.

        debt_schedule (target_debt_ratio): all forecast years converge to median_debt.
        historical median debt = median(500, 520, 550) = 520.
        last ending debt = 550.
        First forecast year: beginning=550, ending=520 → avg=535.
        implied_cod = median(52/500, 55/520) = median(0.1040, 0.1058) ≈ 0.1049.
        Expected interest ≈ -535 × 0.1049 ≈ -56.1
        """
        table = _debt_bearing_table()
        artifact = run_forecast("TST", table, n_years=1)
        fy0 = artifact.forecast_years[0]

        # Reconstruct expected interest using actual drivers
        cod = artifact.drivers["cost_of_debt"]["value"]
        expected_interest = -(fy0.beginning_debt + fy0.ending_debt) / 2.0 * cod
        assert abs(fy0.interest_expense - expected_interest) < 0.5, (
            f"interest_expense {fy0.interest_expense:.2f} should be close to "
            f"avg_debt × cod = {expected_interest:.2f}"
        )

    def test_cost_of_debt_override(self):
        """Manual cost_of_debt_override must be applied directly."""
        table = _debt_bearing_table()
        override = 0.08
        assumptions = ForecastAssumptions(cost_of_debt_override=override)
        artifact = run_forecast("TST", table, n_years=2, assumptions=assumptions)

        assert artifact.drivers["cost_of_debt"]["value"] == override
        assert artifact.drivers["cost_of_debt"]["method"] == "manual_override"

        for fy in artifact.forecast_years:
            if fy.cost_of_debt is not None:
                assert abs(fy.cost_of_debt - override) < 1e-9, (
                    f"Year {fy.year}: cost_of_debt should be {override}, got {fy.cost_of_debt}"
                )


# ---------------------------------------------------------------------------
# 2. Zero-debt company: interest ≈ 0
# ---------------------------------------------------------------------------

class TestZeroDebtCompany:
    """For companies with zero historical debt, interest expense must be zero."""

    def test_interest_expense_is_zero(self):
        table = _zero_debt_table()
        artifact = run_forecast("NODEBT", table, n_years=3)

        for fy in artifact.forecast_years:
            assert fy.interest_expense is not None
            assert abs(fy.interest_expense) < 0.01, (
                f"Year {fy.year}: expected zero interest for zero-debt company, "
                f"got {fy.interest_expense}"
            )

    def test_debt_schedule_method_is_zero_debt_policy(self):
        table = _zero_debt_table()
        artifact = run_forecast("NODEBT", table, n_years=2)
        assert artifact.debt_schedule is not None
        assert artifact.debt_schedule.forecast_method == "zero_debt_policy"

    def test_beginning_and_ending_debt_are_zero(self):
        table = _zero_debt_table()
        artifact = run_forecast("NODEBT", table, n_years=2)
        for fy in artifact.forecast_years:
            assert fy.beginning_debt == 0.0
            assert fy.ending_debt == 0.0


# ---------------------------------------------------------------------------
# 3. Fallback when no debt data
# ---------------------------------------------------------------------------

class TestNoDebtDataFallback:
    """When total_debt.ending is absent, must fall back gracefully."""

    def test_fallback_warning_present(self):
        table = _no_debt_data_table()
        artifact = run_forecast("NODATA", table, n_years=1)
        fallback_warnings = [w for w in artifact.warnings if "Falling back to interest_expense/revenue" in w]
        assert fallback_warnings, (
            f"Expected a fallback warning for missing debt data, got: {artifact.warnings}"
        )

    def test_interest_expense_still_computed(self):
        """Even without debt data, interest_expense must be a finite number."""
        table = _no_debt_data_table()
        artifact = run_forecast("NODATA", table, n_years=2)
        for fy in artifact.forecast_years:
            assert fy.interest_expense is not None
            assert fy.interest_expense <= 0, "Interest expense should be negative (cost)"


# ---------------------------------------------------------------------------
# 4. Debt roll-forward continuity
# ---------------------------------------------------------------------------

class TestDebtRollForward:
    """beginning_debt[year N+1] must equal ending_debt[year N]."""

    def test_debt_continuity_across_years(self):
        table = _debt_bearing_table()
        artifact = run_forecast("TST", table, n_years=4)

        years = artifact.forecast_years
        for i in range(1, len(years)):
            prev_ending = years[i - 1].ending_debt
            curr_beginning = years[i].beginning_debt
            assert prev_ending == curr_beginning, (
                f"Debt continuity broken between {years[i-1].label} and {years[i].label}: "
                f"ending={prev_ending}, next beginning={curr_beginning}"
            )

    def test_first_year_beginning_debt_equals_latest_historical(self):
        """First forecast year beginning_debt must equal last historical ending debt."""
        table = _debt_bearing_table()
        artifact = run_forecast("TST", table, n_years=1)
        fy0 = artifact.forecast_years[0]
        # Last historical ending debt = 550 (2024FY)
        assert fy0.beginning_debt == 550.0, (
            f"First forecast beginning_debt should be 550.0 (last hist ending), "
            f"got {fy0.beginning_debt}"
        )

    def test_net_borrowing_equals_ending_minus_beginning(self):
        """net_borrowing must always equal ending_debt - beginning_debt."""
        table = _debt_bearing_table()
        artifact = run_forecast("TST", table, n_years=3)
        for fy in artifact.forecast_years:
            if fy.beginning_debt is not None and fy.ending_debt is not None:
                expected_nb = fy.ending_debt - fy.beginning_debt
                assert abs((fy.net_borrowing or 0.0) - expected_nb) < 0.01, (
                    f"Year {fy.year}: net_borrowing {fy.net_borrowing} ≠ "
                    f"ending - beginning = {expected_nb}"
                )


# ---------------------------------------------------------------------------
# 5. Equity updated via dividend_schedule (Pass 2)
# ---------------------------------------------------------------------------

class TestEquityUpdatedViaRetainedEarnings:
    """Equity must accumulate via dividend_schedule.retained_earnings_schedule()."""

    def test_equity_increases_by_retained_earnings_each_year(self):
        """equity[t] = equity[t-1] + retained_earnings_addition[t]."""
        table = _debt_bearing_table()
        artifact = run_forecast("TST", table, n_years=3)

        start_eq = 1500.0  # equity.parent for 2024FY
        running = start_eq
        for fy in artifact.forecast_years:
            retained = fy.retained_earnings_addition
            assert retained is not None, f"Year {fy.year}: retained_earnings_addition is None"
            expected_eq = running + retained
            assert abs(fy.equity - expected_eq) < 0.01, (
                f"Year {fy.year}: equity {fy.equity:.2f} ≠ "
                f"prev_equity + retained = {expected_eq:.2f}"
            )
            running = fy.equity

    def test_retained_equals_net_income_minus_cash_dividend(self):
        """retained_earnings_addition must equal net_income - cash_dividend."""
        table = _debt_bearing_table()
        artifact = run_forecast("TST", table, n_years=3)
        for fy in artifact.forecast_years:
            ni = fy.net_income
            div = fy.cash_dividend
            retained = fy.retained_earnings_addition
            if ni is not None and div is not None and retained is not None:
                assert abs(retained - (ni - div)) < 0.01, (
                    f"Year {fy.year}: retained {retained:.2f} ≠ NI {ni:.2f} - div {div:.2f}"
                )

    def test_equity_uses_payout_ratio_not_zero_when_dividends_available(self):
        """When historical dividend data is present, equity should NOT retain 100% of NI."""
        table = _debt_bearing_table()
        artifact = run_forecast("TST", table, n_years=2)
        for fy in artifact.forecast_years:
            ni = fy.net_income
            retained = fy.retained_earnings_addition
            if ni is not None and retained is not None and ni > 0:
                retention_rate = retained / ni
                assert retention_rate < 1.0, (
                    f"Year {fy.year}: retention rate {retention_rate:.2%} should be < 1.0 "
                    "when dividend data is available (not zero-dividend assumption)"
                )

    def test_zero_dividend_when_no_historical_data(self):
        """When dividends_paid.total is absent, payout=0 and retained=net_income."""
        table = _zero_debt_table()  # no dividends_paid.total in fixture
        artifact = run_forecast("NODEBT", table, n_years=2)
        for fy in artifact.forecast_years:
            ni = fy.net_income
            retained = fy.retained_earnings_addition
            if ni is not None and retained is not None:
                assert abs(retained - ni) < 0.01, (
                    f"Year {fy.year}: without dividend data, all NI should be retained. "
                    f"NI={ni:.2f}, retained={retained:.2f}"
                )


# ---------------------------------------------------------------------------
# 6. ForecastYear carries all new fields
# ---------------------------------------------------------------------------

class TestForecastYearNewFields:
    """All new fields on ForecastYear must be populated for debt-bearing companies."""

    def test_beginning_debt_populated(self):
        table = _debt_bearing_table()
        artifact = run_forecast("TST", table, n_years=2)
        for fy in artifact.forecast_years:
            assert fy.beginning_debt is not None, f"Year {fy.year}: beginning_debt is None"

    def test_ending_debt_populated(self):
        table = _debt_bearing_table()
        artifact = run_forecast("TST", table, n_years=2)
        for fy in artifact.forecast_years:
            assert fy.ending_debt is not None, f"Year {fy.year}: ending_debt is None"

    def test_net_borrowing_populated(self):
        table = _debt_bearing_table()
        artifact = run_forecast("TST", table, n_years=2)
        for fy in artifact.forecast_years:
            assert fy.net_borrowing is not None, f"Year {fy.year}: net_borrowing is None"

    def test_cash_dividend_populated_when_historical_data_present(self):
        table = _debt_bearing_table()
        artifact = run_forecast("TST", table, n_years=2)
        for fy in artifact.forecast_years:
            assert fy.cash_dividend is not None, f"Year {fy.year}: cash_dividend is None"

    def test_payout_ratio_populated_when_historical_data_present(self):
        table = _debt_bearing_table()
        artifact = run_forecast("TST", table, n_years=2)
        for fy in artifact.forecast_years:
            assert fy.payout_ratio is not None, f"Year {fy.year}: payout_ratio is None"
            assert 0.0 <= fy.payout_ratio <= 1.0, (
                f"Year {fy.year}: payout_ratio {fy.payout_ratio:.4f} out of [0, 1]"
            )

    def test_retained_earnings_addition_populated(self):
        table = _debt_bearing_table()
        artifact = run_forecast("TST", table, n_years=2)
        for fy in artifact.forecast_years:
            assert fy.retained_earnings_addition is not None, (
                f"Year {fy.year}: retained_earnings_addition is None"
            )

    def test_total_debt_equals_ending_debt(self):
        """total_debt is backward-compatible alias for ending_debt."""
        table = _debt_bearing_table()
        artifact = run_forecast("TST", table, n_years=2)
        for fy in artifact.forecast_years:
            assert fy.total_debt == fy.ending_debt, (
                f"Year {fy.year}: total_debt {fy.total_debt} ≠ ending_debt {fy.ending_debt}"
            )


# ---------------------------------------------------------------------------
# 7. ForecastArtifact.debt_schedule is attached
# ---------------------------------------------------------------------------

class TestDebtScheduleAttachedToArtifact:

    def test_debt_schedule_is_not_none(self):
        table = _debt_bearing_table()
        artifact = run_forecast("TST", table, n_years=2)
        assert artifact.debt_schedule is not None

    def test_debt_schedule_has_forecast_rows(self):
        table = _debt_bearing_table()
        artifact = run_forecast("TST", table, n_years=3)
        assert len(artifact.debt_schedule.forecast_rows) == 3

    def test_to_dict_includes_debt_schedule(self):
        table = _debt_bearing_table()
        artifact = run_forecast("TST", table, n_years=2)
        d = artifact.to_dict()
        assert "debt_schedule" in d
        assert d["debt_schedule"] is not None


# ---------------------------------------------------------------------------
# 8. to_dict serialises all new fields
# ---------------------------------------------------------------------------

class TestToDictNewFields:

    def test_all_new_debt_fields_in_to_dict(self):
        table = _debt_bearing_table()
        artifact = run_forecast("TST", table, n_years=2)
        d = artifact.to_dict()
        for year_dict in d["forecast_years"]:
            for key in ("beginning_debt", "ending_debt", "net_borrowing", "cost_of_debt"):
                assert key in year_dict, (
                    f"to_dict() missing '{key}' for year {year_dict.get('year')}"
                )

    def test_all_new_dividend_fields_in_to_dict(self):
        table = _debt_bearing_table()
        artifact = run_forecast("TST", table, n_years=2)
        d = artifact.to_dict()
        for year_dict in d["forecast_years"]:
            for key in ("cash_dividend", "payout_ratio", "retained_earnings_addition"):
                assert key in year_dict, (
                    f"to_dict() missing '{key}' for year {year_dict.get('year')}"
                )

    def test_cost_of_debt_in_drivers(self):
        table = _debt_bearing_table()
        artifact = run_forecast("TST", table, n_years=1)
        d = artifact.to_dict()
        assert "cost_of_debt" in d["drivers"]

    def test_interest_to_revenue_not_in_drivers(self):
        """Old revenue-based interest driver must no longer appear in drivers."""
        table = _debt_bearing_table()
        artifact = run_forecast("TST", table, n_years=1)
        d = artifact.to_dict()
        assert "interest_to_revenue" not in d["drivers"], (
            "interest_to_revenue should be removed from drivers dict (replaced by cost_of_debt)"
        )


# ---------------------------------------------------------------------------
# 9. Balance sheet identity
# ---------------------------------------------------------------------------

class TestBalanceSheetIdentity:
    """total_assets == equity + ending_debt + other_liabilities for every forecast year."""

    def test_balance_sheet_identity_holds(self):
        table = _debt_bearing_table()
        artifact = run_forecast("TST", table, n_years=3)
        for fy in artifact.forecast_years:
            if all(v is not None for v in [fy.total_assets, fy.equity, fy.ending_debt, fy.other_liabilities]):
                lhs = fy.total_assets
                rhs = fy.equity + fy.ending_debt + fy.other_liabilities
                assert abs(lhs - rhs) < 0.1, (
                    f"Year {fy.year}: total_assets {lhs:.1f} ≠ "
                    f"equity + debt + other_liab = {rhs:.1f}"
                )

    def test_balance_sheet_identity_zero_debt(self):
        table = _zero_debt_table()
        artifact = run_forecast("NODEBT", table, n_years=2)
        for fy in artifact.forecast_years:
            if all(v is not None for v in [fy.total_assets, fy.equity, fy.other_liabilities]):
                lhs = fy.total_assets
                rhs = fy.equity + (fy.ending_debt or 0.0) + fy.other_liabilities
                assert abs(lhs - rhs) < 0.1, (
                    f"Year {fy.year}: balance sheet identity broken for zero-debt company"
                )
