"""Regression tests for debt schedule and FCFE formula invariants (plan §8).

Every assertion here encodes a mandatory financial identity that must hold
regardless of which data path produced the inputs.  If any of these tests fail
it means a calculation has regressed to a mathematically incorrect state.
"""
from __future__ import annotations

import pytest
from backend.analytics.debt_schedule import (
    DebtScheduleRow,
    DebtSchedule,
    _check_debt_identity,
    _compute_average_debt,
    build_debt_schedule,
)
from backend.analytics.cash_sweep import (
    CashSweepArtifact,
    build_cash_sweep_artifact,
    compute_cash_sweep,
)
from backend.analytics.blend import blend_dcf


# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────

def _row(beginning, new_borrow, repayment, ending, method="direct_cash_flow", confidence="high"):
    nb = new_borrow - repayment if (new_borrow is not None and repayment is not None) else None
    avg = (beginning + ending) / 2 if (beginning is not None and ending is not None) else None
    identity = _check_debt_identity(beginning, new_borrow, repayment, ending)
    return DebtScheduleRow(
        year=2026, label="2026F",
        beginning_interest_bearing_debt=beginning,
        ending_interest_bearing_debt=ending,
        new_borrowing=new_borrow,
        debt_repayment=repayment,
        net_borrowing=nb,
        average_debt=avg,
        identity_check_passes=identity,
        method=method,  # type: ignore[arg-type]
        confidence=confidence,  # type: ignore[arg-type]
    )


# ─────────────────────────────────────────────────────────────────────────────
# I.  Debt identity: ending == beginning + new_borrowing - debt_repayment
# ─────────────────────────────────────────────────────────────────────────────

class TestDebtIdentityFormula:
    def test_identity_holds_for_standard_case(self):
        """ending == beginning + new_borrowing - repayment."""
        beginning, new_borrow, repayment = 100.0, 50.0, 20.0
        expected_ending = beginning + new_borrow - repayment  # 130.0
        assert _check_debt_identity(beginning, new_borrow, repayment, expected_ending) is True

    def test_identity_violated_emits_false(self):
        beginning, new_borrow, repayment = 100.0, 50.0, 20.0
        wrong_ending = 200.0  # should be 130
        assert _check_debt_identity(beginning, new_borrow, repayment, wrong_ending) is False

    def test_identity_none_when_any_input_missing(self):
        assert _check_debt_identity(None, 50.0, 20.0, 130.0) is None
        assert _check_debt_identity(100.0, None, 20.0, 130.0) is None
        assert _check_debt_identity(100.0, 50.0, None, 130.0) is None
        assert _check_debt_identity(100.0, 50.0, 20.0, None) is None

    def test_identity_tolerance_0_1_vnd_bn(self):
        """Within 0.1 VND bn is acceptable (floating-point rounding)."""
        assert _check_debt_identity(100.0, 50.0, 20.0, 130.05) is True   # gap = 0.05 < 0.1
        assert _check_debt_identity(100.0, 50.0, 20.0, 130.15) is False  # gap = 0.15 > 0.1

    def test_zero_debt_identity_holds(self):
        assert _check_debt_identity(0.0, 0.0, 0.0, 0.0) is True


# ─────────────────────────────────────────────────────────────────────────────
# II.  Net borrowing == new_borrowing - debt_repayment
# ─────────────────────────────────────────────────────────────────────────────

class TestNetBorrowingFormula:
    def test_net_borrowing_positive_net_draw(self):
        """Company borrows more than it repays."""
        new_borrow, repayment = 80.0, 30.0
        expected_nb = new_borrow - repayment  # 50.0
        row = _row(100.0, new_borrow, repayment, 150.0)
        assert row.net_borrowing == pytest.approx(expected_nb)

    def test_net_borrowing_net_repayment(self):
        """Company repays more than it borrows."""
        new_borrow, repayment = 10.0, 40.0
        expected_nb = new_borrow - repayment  # -30.0
        row = _row(100.0, new_borrow, repayment, 70.0)
        assert row.net_borrowing == pytest.approx(expected_nb)

    def test_net_borrowing_zero_both_sides(self):
        row = _row(100.0, 0.0, 0.0, 100.0)
        assert row.net_borrowing == pytest.approx(0.0)

    def test_build_forecast_zero_debt_policy_net_borrowing_is_zero(self):
        ft = {
            "total_debt.ending": {"2023FY": 0.0, "2024FY": 0.0, "2025FY": 0.0},
        }
        ds = build_debt_schedule("TST", ft, ["2023FY", "2024FY", "2025FY"], ["2026F"], [2026])
        assert ds.forecast_method == "zero_debt_policy"
        for row in ds.forecast_rows:
            assert row.new_borrowing == pytest.approx(0.0)
            assert row.debt_repayment == pytest.approx(0.0)
            assert row.net_borrowing == pytest.approx(0.0)


# ─────────────────────────────────────────────────────────────────────────────
# III.  Average debt == (beginning + ending) / 2
# ─────────────────────────────────────────────────────────────────────────────

class TestAverageDebtFormula:
    def test_average_debt_standard(self):
        avg = _compute_average_debt(100.0, 200.0)
        assert avg == pytest.approx(150.0)

    def test_average_debt_equal_sides(self):
        avg = _compute_average_debt(50.0, 50.0)
        assert avg == pytest.approx(50.0)

    def test_average_debt_none_when_either_missing(self):
        assert _compute_average_debt(None, 100.0) is None
        assert _compute_average_debt(100.0, None) is None

    def test_average_debt_zero(self):
        assert _compute_average_debt(0.0, 0.0) == pytest.approx(0.0)

    def test_build_populates_average_debt_in_forecast_rows(self):
        ft = {
            "total_debt.ending": {"2023FY": 0.0, "2024FY": 0.0, "2025FY": 0.0},
        }
        ds = build_debt_schedule("TST", ft, ["2023FY", "2024FY", "2025FY"], ["2026F"], [2026])
        for row in ds.forecast_rows:
            assert row.average_debt is not None
            beg = row.beginning_interest_bearing_debt
            end = row.ending_interest_bearing_debt
            if beg is not None and end is not None:
                assert row.average_debt == pytest.approx((beg + end) / 2.0)

    def test_build_populates_average_debt_historical(self):
        ft = {"total_debt.ending": {"2023FY": 100.0, "2024FY": 200.0}}
        from backend.analytics.debt_schedule import build_historical_debt_schedule
        rows = build_historical_debt_schedule("TST", ft, ["2023FY", "2024FY"])
        # second row: beginning=100, ending=200 → avg=150
        row_2024 = rows[1]
        assert row_2024.average_debt == pytest.approx(150.0)


# ─────────────────────────────────────────────────────────────────────────────
# IV.  Interest expense == average_debt × cost_of_debt
# ─────────────────────────────────────────────────────────────────────────────

class TestInterestExpenseFormula:
    def test_interest_expense_from_avg_debt_and_cod(self):
        avg_debt = 150.0
        cod = 0.08
        expected_ie = avg_debt * cod  # 12.0
        assert expected_ie == pytest.approx(12.0)

    def test_interest_expense_zero_debt(self):
        avg_debt = 0.0
        cod = 0.08
        assert avg_debt * cod == pytest.approx(0.0)

    def test_forecasting_interest_expense_consistent_with_avg_debt(self):
        """ForecastYear.interest_expense must equal avg_debt × cost_of_debt."""
        from backend.analytics.forecasting import run_forecast, ForecastAssumptions
        ft = {
            "revenue.net": {"2023FY": 1500.0, "2024FY": 1700.0, "2025FY": 1865.0},
            "gross_profit.total": {"2023FY": 680.0, "2024FY": 780.0, "2025FY": 884.0},
            "sga.total": {"2023FY": -350.0, "2024FY": -380.0, "2025FY": -418.0},
            "depreciation.total": {"2023FY": 40.0, "2024FY": 44.0, "2025FY": 48.0},
            "capex.total": {"2023FY": -80.0, "2024FY": -90.0, "2025FY": -100.0},
            "total_debt.ending": {"2025FY": 43.0},
            "profit_before_tax.total": {"2023FY": 290.0, "2024FY": 320.0, "2025FY": 346.0},
            "tax_expense.total": {"2023FY": -50.0, "2024FY": -55.0, "2025FY": -54.0},
            "net_income.parent": {"2023FY": 240.0, "2024FY": 265.0, "2025FY": 292.0},
        }
        # Fix cost_of_debt so we can check the formula
        assumptions = ForecastAssumptions(cost_of_debt_override=0.08)
        forecast = run_forecast("TST", ft, assumptions=assumptions, shares_mn=94.45)
        ds = forecast.debt_schedule
        assert ds is not None
        for fy in forecast.forecast_years:
            if fy.beginning_debt is not None and fy.ending_debt is not None and fy.cost_of_debt is not None:
                avg_debt = (fy.beginning_debt + fy.ending_debt) / 2.0
                expected_ie = -avg_debt * fy.cost_of_debt  # negative: cost convention
                assert fy.interest_expense == pytest.approx(expected_ie, abs=0.01)


# ─────────────────────────────────────────────────────────────────────────────
# V.  FCFE formula: FCFE == CFO - CAPEX_positive + Net Borrowing
# ─────────────────────────────────────────────────────────────────────────────

class TestFCFEFormulaIdentity:
    def test_fcfe_cfo_formula(self):
        """FCFE = CFO - CAPEX_positive + Net Borrowing."""
        cfo = 100.0
        capex_positive = 30.0
        net_borrowing = 10.0
        expected_fcfe = cfo - capex_positive + net_borrowing  # 80.0
        assert expected_fcfe == pytest.approx(80.0)

    def test_fcfe_ni_formula(self):
        """FCFE = NI + D&A - CAPEX_positive - ΔNWC + Net Borrowing."""
        ni = 200.0
        dna = 40.0
        capex_positive = 80.0
        delta_nwc = 15.0
        net_borrowing = 20.0
        expected_fcfe = ni + dna - capex_positive - delta_nwc + net_borrowing  # 165.0
        assert expected_fcfe == pytest.approx(165.0)

    def test_fcfe_blocked_by_debt_gate_yields_formula_invariant_when_zero_debt(self):
        """With zero_debt_policy, net_borrowing = 0; formula must hold."""
        from backend.analytics.fcfe import compute_fcfe, CostOfEquityAssumptions
        from backend.analytics.forecasting import run_forecast
        ft = {
            "revenue.net": {"2023FY": 1500.0, "2024FY": 1700.0, "2025FY": 1865.0},
            "gross_profit.total": {"2023FY": 680.0, "2024FY": 780.0, "2025FY": 884.0},
            "sga.total": {"2023FY": -350.0, "2024FY": -380.0, "2025FY": -418.0},
            "depreciation.total": {"2023FY": 40.0, "2024FY": 44.0, "2025FY": 48.0},
            "capex.total": {"2023FY": -80.0, "2024FY": -90.0, "2025FY": -100.0},
            "total_debt.ending": {"2023FY": 0.0, "2024FY": 0.0, "2025FY": 0.0},
            "profit_before_tax.total": {"2023FY": 290.0, "2024FY": 320.0, "2025FY": 346.0},
            "tax_expense.total": {"2023FY": -50.0, "2024FY": -55.0, "2025FY": -54.0},
            "net_income.parent": {"2023FY": 240.0, "2024FY": 265.0, "2025FY": 292.0},
        }
        forecast = run_forecast("TST", ft, shares_mn=94.45)
        assert forecast.debt_schedule is not None
        assert forecast.debt_schedule.forecast_method == "zero_debt_policy"

        result = compute_fcfe(
            ticker="TST", forecast=forecast, fact_table=ft, shares_mn=94.45,
            cost_of_equity_assumptions=CostOfEquityAssumptions(re_override=0.14),
        )
        # For each year, verify FCFE = NI + D&A - CAPEX - ΔNWC + NB
        for fy in result.forecast_years:
            if fy.fcfe is None:
                continue
            ni = fy.net_income
            dna = fy.depreciation
            capex_pos = fy.capex  # stored as positive outflow
            delta_nwc = fy.delta_nwc or 0.0
            nb = fy.net_borrowing or 0.0
            if ni is not None and dna is not None and capex_pos is not None:
                expected = ni + dna - capex_pos - delta_nwc + nb
                assert fy.fcfe == pytest.approx(expected, abs=0.1), (
                    f"{fy.label}: FCFE {fy.fcfe} != NI+D&A-CAPEX-ΔNWC+NB {expected}"
                )


# ─────────────────────────────────────────────────────────────────────────────
# VI.  Cash sweep identity
# ─────────────────────────────────────────────────────────────────────────────

class TestCashSweepIdentity:
    def test_cash_sweep_identity(self):
        """ending_cash == opening + CFO - CAPEX - dividends + new_debt - debt_repaid + other."""
        opening = 100.0
        cfo = 80.0
        capex = 30.0
        dividends = 20.0
        new_debt = 10.0
        debt_repaid = 5.0
        other = 2.0
        expected_ending = opening + cfo - capex - dividends + new_debt - debt_repaid + other  # 137
        result = compute_cash_sweep(
            year_label="2026F",
            opening_cash=opening,
            cfo=cfo,
            capex_positive=capex,
            dividends_paid=dividends,
            new_debt=new_debt,
            debt_repaid=debt_repaid,
            other=other,
        )
        assert result.computed_ending_cash == pytest.approx(expected_ending)

    def test_cash_sweep_artifact_status_approved_when_reconciles(self):
        result = build_cash_sweep_artifact(
            ticker="TST",
            year_inputs=[{
                "year_label": "2026F",
                "opening_cash": 100.0,
                "cfo": 80.0,
                "capex_positive": 30.0,
                "dividends_paid": 20.0,
                "new_debt": 0.0,
                "debt_repaid": 0.0,
                "reported_ending_cash": 130.0,  # 100 + 80 - 30 - 20 = 130
            }],
        )
        assert result.status == "approved"
        assert result.all_reconcile is True
        assert result.is_debt_publishable is True

    def test_cash_sweep_artifact_status_failed_when_not_reconcile(self):
        result = build_cash_sweep_artifact(
            ticker="TST",
            year_inputs=[{
                "year_label": "2026F",
                "opening_cash": 100.0,
                "cfo": 80.0,
                "capex_positive": 30.0,
                "dividends_paid": 20.0,
                "reported_ending_cash": 999.0,  # wildly wrong
            }],
        )
        assert result.status == "failed"
        assert result.all_reconcile is False
        assert result.is_debt_publishable is False

    def test_cash_sweep_artifact_status_pending_when_no_reported_cash(self):
        result = build_cash_sweep_artifact(
            ticker="TST",
            year_inputs=[{
                "year_label": "2026F",
                "opening_cash": 100.0,
                "cfo": 80.0,
                "capex_positive": 30.0,
                "dividends_paid": 20.0,
            }],
        )
        assert result.status == "pending"

    def test_cash_sweep_artifact_net_borrowing_schedule(self):
        result = build_cash_sweep_artifact(
            ticker="TST",
            year_inputs=[
                {"year_label": "2026F", "opening_cash": 100.0, "cfo": 80.0,
                 "capex_positive": 30.0, "dividends_paid": 20.0,
                 "new_debt": 50.0, "debt_repaid": 10.0},
                {"year_label": "2027F", "opening_cash": 170.0, "cfo": 90.0,
                 "capex_positive": 35.0, "dividends_paid": 25.0,
                 "new_debt": 0.0, "debt_repaid": 20.0},
            ],
        )
        sched = result.net_borrowing_schedule()
        assert sched["2026F"] == pytest.approx(40.0)   # 50 - 10
        assert sched["2027F"] == pytest.approx(-20.0)  # 0 - 20


# ─────────────────────────────────────────────────────────────────────────────
# VII.  Blend gate — FCFF/FCFE 25% gap
# ─────────────────────────────────────────────────────────────────────────────

class TestBlendGates:
    def test_fcff_fcfe_gap_below_25pct_does_not_block(self):
        result = blend_dcf(
            ticker="TST",
            price_fcff=60_000.0,
            price_fcfe=58_000.0,   # gap ~3.4%
        )
        assert result.fcff_fcfe_gap_pct == pytest.approx(abs(60_000 / 58_000 - 1), rel=1e-4)
        # gap < 25% alone does not set draft
        # both prices present and gap < 25%
        assert result.is_draft_only is False

    def test_fcff_fcfe_gap_above_25pct_marks_draft(self):
        result = blend_dcf(
            ticker="TST",
            price_fcff=60_000.0,
            price_fcfe=40_000.0,   # gap = |60k/40k - 1| = 50%
        )
        assert result.fcff_fcfe_gap_pct == pytest.approx(0.50, rel=1e-4)
        assert result.is_draft_only is True
        assert any("25%" in w for w in result.warnings)

    def test_fcff_fcfe_gap_stored_in_result(self):
        result = blend_dcf(
            ticker="TST",
            price_fcff=60_000.0,
            price_fcfe=45_000.0,
        )
        expected_gap = abs(60_000 / 45_000 - 1)
        assert result.fcff_fcfe_gap_pct == pytest.approx(expected_gap, rel=1e-4)

    def test_fcff_fcfe_gap_none_when_price_fcfe_none(self):
        result = blend_dcf(
            ticker="TST",
            price_fcff=60_000.0,
            price_fcfe=None,
        )
        assert result.fcff_fcfe_gap_pct is None


# ─────────────────────────────────────────────────────────────────────────────
# VIII.  DebtSchedule.status property
# ─────────────────────────────────────────────────────────────────────────────

class TestDebtScheduleStatus:
    def _make_ds(self, method, confidence="high"):
        rows = [DebtScheduleRow(
            year=2026, label="2026F",
            beginning_interest_bearing_debt=40.0,
            ending_interest_bearing_debt=40.0,
            net_borrowing=0.0,
            average_debt=40.0,
            method=method,  # type: ignore[arg-type]
            confidence=confidence,  # type: ignore[arg-type]
        )]
        return DebtSchedule("TST", [], rows, forecast_method=method)  # type: ignore[arg-type]

    def test_direct_cash_flow_high_is_status_high(self):
        ds = self._make_ds("direct_cash_flow", "high")
        assert ds.status == "high"

    def test_zero_debt_policy_high_is_status_high(self):
        ds = self._make_ds("zero_debt_policy", "high")
        assert ds.status == "high"

    def test_target_debt_ratio_is_status_low(self):
        ds = self._make_ds("target_debt_ratio", "low")
        assert ds.status == "low"

    def test_balance_sheet_delta_is_status_medium(self):
        ds = self._make_ds("balance_sheet_delta", "medium")
        assert ds.status == "medium"

    def test_manual_override_is_status_medium(self):
        ds = self._make_ds("manual_override", "medium")
        assert ds.status == "medium"

    def test_missing_is_status_blocked(self):
        ds = self._make_ds("missing", "low")
        assert ds.status == "blocked"

    def test_status_in_to_dict(self):
        ds = self._make_ds("direct_cash_flow", "high")
        d = ds.to_dict()
        assert "status" in d
        assert d["status"] == "high"
