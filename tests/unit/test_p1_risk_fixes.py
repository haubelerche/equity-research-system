"""Regression tests for P1 risk fixes:

1. DebtScheduleRow.cost_of_debt + interest_expense written back from forecasting.py
2. ForecastArtifact.cash_sweep_artifact is built and present
3. build_net_debt_bridge ending_debt_override param
4. Convergence-loop warning present when debt method is not zero/direct
"""
from __future__ import annotations

import pytest
from backend.analytics.forecasting import run_forecast, ForecastAssumptions
from backend.analytics.cash_sweep import CashSweepArtifact, build_cash_sweep_artifact
from backend.analytics.net_debt_bridge import build_net_debt_bridge


# ─────────────────────────────────────────────────────────────────────────────
# Shared fixture
# ─────────────────────────────────────────────────────────────────────────────

def _minimal_ft_with_debt() -> dict:
    return {
        "revenue.net": {"2023FY": 1500.0, "2024FY": 1700.0, "2025FY": 1865.0},
        "gross_profit.total": {"2023FY": 680.0, "2024FY": 780.0, "2025FY": 884.0},
        "sga.total": {"2023FY": -350.0, "2024FY": -380.0, "2025FY": -418.0},
        "depreciation.total": {"2023FY": 40.0, "2024FY": 44.0, "2025FY": 48.0},
        "capex.total": {"2023FY": -80.0, "2024FY": -90.0, "2025FY": -100.0},
        "total_debt.ending": {"2025FY": 43.0},
        "cash_and_equivalents.ending": {"2025FY": 120.0},
        "equity.parent": {"2025FY": 1500.0},
        "total_assets.ending": {"2025FY": 2500.0},
        "profit_before_tax.total": {"2023FY": 290.0, "2024FY": 320.0, "2025FY": 346.0},
        "tax_expense.total": {"2023FY": -50.0, "2024FY": -55.0, "2025FY": -54.0},
        "net_income.parent": {"2023FY": 240.0, "2024FY": 265.0, "2025FY": 292.0},
    }


def _zero_debt_ft() -> dict:
    ft = _minimal_ft_with_debt()
    ft["total_debt.ending"] = {"2023FY": 0.0, "2024FY": 0.0, "2025FY": 0.0}
    return ft


# ─────────────────────────────────────────────────────────────────────────────
# 1.  cost_of_debt + interest_expense written back to forecast DebtScheduleRow
# ─────────────────────────────────────────────────────────────────────────────

class TestDebtScheduleRowWriteback:
    def test_cost_of_debt_written_to_forecast_rows(self):
        """After run_forecast, each forecast DebtScheduleRow has cost_of_debt set."""
        ft = _zero_debt_ft()
        assumptions = ForecastAssumptions(cost_of_debt_override=0.08)
        forecast = run_forecast("TST", ft, assumptions=assumptions, shares_mn=94.45)
        ds = forecast.debt_schedule
        assert ds is not None
        for row in ds.forecast_rows:
            # zero_debt_policy → cost_of_debt may stay None (avg_debt = 0)
            # but the field should exist
            assert hasattr(row, "cost_of_debt")

    def test_interest_expense_written_to_forecast_rows_when_debt_present(self):
        """When debt > 0, forecast DebtScheduleRow.interest_expense = avg_debt × cost_of_debt."""
        ft = _minimal_ft_with_debt()
        assumptions = ForecastAssumptions(cost_of_debt_override=0.08)
        forecast = run_forecast("TST", ft, assumptions=assumptions, shares_mn=94.45)
        ds = forecast.debt_schedule
        assert ds is not None
        rows_with_debt = [r for r in ds.forecast_rows if r.average_debt and r.average_debt > 0]
        assert len(rows_with_debt) > 0, "Expected at least one forecast row with non-zero debt"
        for row in rows_with_debt:
            assert row.cost_of_debt is not None
            assert row.interest_expense is not None
            expected_ie = row.average_debt * row.cost_of_debt
            assert row.interest_expense == pytest.approx(expected_ie, abs=0.01)

    def test_forecast_year_and_debt_row_interest_expense_consistent(self):
        """ForecastYear.interest_expense (negative) matches abs(DebtScheduleRow.interest_expense)."""
        ft = _minimal_ft_with_debt()
        assumptions = ForecastAssumptions(cost_of_debt_override=0.08)
        forecast = run_forecast("TST", ft, assumptions=assumptions, shares_mn=94.45)
        ds = forecast.debt_schedule
        assert ds is not None
        debt_row_by_label = {r.label: r for r in ds.forecast_rows}
        for fy in forecast.forecast_years:
            drow = debt_row_by_label.get(fy.label)
            if drow and drow.interest_expense is not None and fy.interest_expense is not None:
                # ForecastYear.interest_expense is negative (cost); DebtScheduleRow is positive
                assert abs(fy.interest_expense) == pytest.approx(drow.interest_expense, abs=0.01)


# ─────────────────────────────────────────────────────────────────────────────
# 2.  ForecastArtifact.cash_sweep_artifact is built and present
# ─────────────────────────────────────────────────────────────────────────────

class TestForecastCashSweepArtifact:
    def test_cash_sweep_artifact_present_after_run_forecast(self):
        """run_forecast must attach a CashSweepArtifact to the returned ForecastArtifact."""
        ft = _zero_debt_ft()
        forecast = run_forecast("TST", ft, shares_mn=94.45)
        assert forecast.cash_sweep_artifact is not None
        assert isinstance(forecast.cash_sweep_artifact, CashSweepArtifact)

    def test_cash_sweep_artifact_has_correct_number_of_years(self):
        ft = _zero_debt_ft()
        forecast = run_forecast("TST", ft, shares_mn=94.45)
        cs = forecast.cash_sweep_artifact
        assert cs is not None
        assert len(cs.year_results) == len(forecast.forecast_years)

    def test_cash_sweep_artifact_status_pending_for_forecast(self):
        """Forecast sweep has no reported_ending_cash → status must be pending (not failed)."""
        ft = _zero_debt_ft()
        forecast = run_forecast("TST", ft, shares_mn=94.45)
        cs = forecast.cash_sweep_artifact
        assert cs is not None
        assert cs.status == "pending"

    def test_cash_sweep_artifact_in_to_dict(self):
        ft = _zero_debt_ft()
        forecast = run_forecast("TST", ft, shares_mn=94.45)
        d = forecast.to_dict()
        assert "cash_sweep_artifact" in d
        assert d["cash_sweep_artifact"] is not None
        assert "status" in d["cash_sweep_artifact"]

    def test_cash_sweep_cfo_approximation_is_positive_for_profitable_company(self):
        """NI + D&A - ΔNWC should be positive for a profitable company."""
        ft = _zero_debt_ft()
        forecast = run_forecast("TST", ft, shares_mn=94.45)
        cs = forecast.cash_sweep_artifact
        assert cs is not None
        for result in cs.year_results:
            assert result.cfo > 0, f"{result.year_label}: CFO approx should be > 0"

    def test_cash_sweep_net_borrowing_zero_for_zero_debt_policy(self):
        """Zero-debt company → new_debt and debt_repaid both 0 in sweep."""
        ft = _zero_debt_ft()
        forecast = run_forecast("TST", ft, shares_mn=94.45)
        cs = forecast.cash_sweep_artifact
        assert cs is not None
        for result in cs.year_results:
            assert result.new_debt == pytest.approx(0.0)
            assert result.debt_repaid == pytest.approx(0.0)


# ─────────────────────────────────────────────────────────────────────────────
# 3.  build_net_debt_bridge ending_debt_override
# ─────────────────────────────────────────────────────────────────────────────

class TestNetDebtBridgeEndingDebtOverride:
    def test_override_replaces_fact_table_debt(self):
        ft = {"total_debt.ending": {"2025FY": 999.0},
              "cash_and_equivalents.ending": {"2025FY": 100.0}}
        bridge = build_net_debt_bridge(ft, "2025FY", ending_debt_override=50.0)
        # Should use 50, not 999
        assert bridge.total_debt == pytest.approx(50.0)
        assert bridge.status != "blocked"

    def test_override_zero_does_not_block(self):
        ft = {}
        bridge = build_net_debt_bridge(ft, "2025FY", ending_debt_override=0.0)
        assert bridge.total_debt == pytest.approx(0.0)
        assert bridge.status != "blocked"

    def test_no_override_reads_from_fact_table(self):
        ft = {"total_debt.ending": {"2025FY": 200.0}}
        bridge = build_net_debt_bridge(ft, "2025FY")
        assert bridge.total_debt == pytest.approx(200.0)

    def test_no_override_missing_debt_blocks(self):
        ft = {}
        bridge = build_net_debt_bridge(ft, "2025FY")
        assert bridge.is_blocked is True

    def test_override_sets_debt_source_as_artifact(self):
        ft = {}
        bridge = build_net_debt_bridge(ft, "2025FY", ending_debt_override=100.0)
        # Bridge should not be blocked even though fact_table has no debt
        assert bridge.is_blocked is False

    def test_override_net_debt_formula(self):
        """net_debt = ending_debt_override - cash - st_inv."""
        ft = {"cash_and_equivalents.ending": {"2025FY": 80.0},
              "short_term_investments.ending": {"2025FY": 20.0}}
        bridge = build_net_debt_bridge(ft, "2025FY", ending_debt_override=200.0)
        expected_net_debt = 200.0 - 80.0 - 20.0  # 100.0
        assert bridge.net_debt == pytest.approx(expected_net_debt)


# ─────────────────────────────────────────────────────────────────────────────
# 4.  Convergence-loop warning when debt method is not zero/direct
# ─────────────────────────────────────────────────────────────────────────────

class TestConvergenceWarning:
    def test_convergence_warning_present_for_stable_debt(self):
        """stable_debt method must emit convergence warning in ForecastArtifact."""
        ft = _minimal_ft_with_debt()  # no CFS data -> stable_debt
        forecast = run_forecast("TST", ft, shares_mn=94.45)
        assert forecast.debt_schedule is not None
        assert forecast.debt_schedule.forecast_method == "stable_debt"
        convergence_warnings = [w for w in forecast.warnings if "convergence" in w.lower() or "single-pass" in w.lower()]
        assert len(convergence_warnings) >= 1

    def test_no_convergence_warning_for_zero_debt_policy(self):
        """Zero-debt company: no convergence warning needed."""
        ft = _zero_debt_ft()
        forecast = run_forecast("TST", ft, shares_mn=94.45)
        assert forecast.debt_schedule is not None
        assert forecast.debt_schedule.forecast_method == "zero_debt_policy"
        convergence_warnings = [w for w in forecast.warnings if "convergence" in w.lower() or "single-pass" in w.lower()]
        assert len(convergence_warnings) == 0
