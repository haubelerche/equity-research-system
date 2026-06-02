"""Tests for backend/analytics/cash_sweep.py — cash reconciliation and equity roll-forward.

Covers:
- Normal cash sweep reconciliation
- Cash sweep that does not reconcile
- Negative CAPEX input auto-corrected
- Equity roll-forward normal case
- Equity without dividend deduction (dividends_paid=0 warning)
- Debt flow mismatch detection
- Tolerance boundaries
"""
from __future__ import annotations

import pytest

from backend.analytics.cash_sweep import (
    CashSweepResult,
    EquityRollForwardResult,
    check_debt_flow_mismatch,
    check_equity_roll_forward,
    compute_cash_sweep,
)


# ---------------------------------------------------------------------------
# compute_cash_sweep
# ---------------------------------------------------------------------------


class TestComputeCashSweep:
    def test_normal_case_reconciles(self):
        """Standard profitable year: CFO funds CAPEX and dividends."""
        result = compute_cash_sweep(
            year_label="2025FY",
            opening_cash=100.0,
            cfo=80.0,
            capex_positive=30.0,
            dividends_paid=20.0,
            new_debt=0.0,
            debt_repaid=0.0,
            reported_ending_cash=130.0,
        )
        # 100 + 80 - 30 - 20 = 130
        assert isinstance(result, CashSweepResult)
        assert result.computed_ending_cash == pytest.approx(130.0)
        assert result.reconciles is True
        assert result.warnings == []

    def test_reconciliation_fails_beyond_tolerance(self):
        """Reported cash differs by more than 5% relative."""
        result = compute_cash_sweep(
            year_label="2025FY",
            opening_cash=100.0,
            cfo=80.0,
            capex_positive=30.0,
            dividends_paid=20.0,
            reported_ending_cash=200.0,  # computed = 130, reported = 200 → 53% gap
        )
        assert result.computed_ending_cash == pytest.approx(130.0)
        assert result.reconciles is False
        assert len(result.warnings) >= 1
        assert "reconcile" in result.warnings[0].lower()

    def test_reconciliation_within_tolerance(self):
        """Small rounding difference within 5% tolerance should reconcile."""
        result = compute_cash_sweep(
            year_label="2025FY",
            opening_cash=100.0,
            cfo=80.0,
            capex_positive=30.0,
            dividends_paid=20.0,
            reported_ending_cash=132.0,  # computed = 130, gap = 2/132 ≈ 1.5%
        )
        assert result.reconciles is True
        assert result.warnings == []

    def test_with_debt_activity(self):
        """New debt and repayment affect ending cash correctly."""
        result = compute_cash_sweep(
            year_label="2025FY",
            opening_cash=50.0,
            cfo=40.0,
            capex_positive=20.0,
            dividends_paid=10.0,
            new_debt=30.0,
            debt_repaid=15.0,
            reported_ending_cash=75.0,
        )
        # 50 + 40 - 20 - 10 + 30 - 15 = 75
        assert result.computed_ending_cash == pytest.approx(75.0)
        assert result.reconciles is True

    def test_with_st_investments_and_other(self):
        """Short-term investments and catch-all flows are included."""
        result = compute_cash_sweep(
            year_label="2025FY",
            opening_cash=100.0,
            cfo=60.0,
            capex_positive=20.0,
            dividends_paid=10.0,
            delta_st_investments=15.0,  # cash deployed to ST deposits
            other=5.0,
            reported_ending_cash=120.0,
        )
        # 100 + 60 - 20 - 10 - 15 + 5 = 120
        assert result.computed_ending_cash == pytest.approx(120.0)
        assert result.reconciles is True

    def test_no_reported_cash_always_reconciles(self):
        """When no reported_ending_cash is given, reconciles defaults to True."""
        result = compute_cash_sweep(
            year_label="2025FY",
            opening_cash=100.0,
            cfo=50.0,
            capex_positive=30.0,
            dividends_paid=10.0,
        )
        assert result.reconciles is True
        assert result.reported_ending_cash is None

    def test_negative_capex_input_auto_converted(self):
        """If capex_positive is accidentally passed as negative, abs() is applied."""
        result = compute_cash_sweep(
            year_label="2025FY",
            opening_cash=100.0,
            cfo=80.0,
            capex_positive=-30.0,   # wrong sign — should be auto-corrected
            dividends_paid=20.0,
            reported_ending_cash=130.0,
        )
        assert result.capex == pytest.approx(30.0)
        assert result.computed_ending_cash == pytest.approx(130.0)
        assert result.reconciles is True
        assert any("abs()" in w or "negative" in w.lower() for w in result.warnings)

    def test_negative_dividends_auto_converted(self):
        """Negative dividends_paid should be converted to positive with warning."""
        result = compute_cash_sweep(
            year_label="2025FY",
            opening_cash=100.0,
            cfo=80.0,
            capex_positive=30.0,
            dividends_paid=-20.0,
            reported_ending_cash=130.0,
        )
        assert result.dividends_paid == pytest.approx(20.0)
        assert result.reconciles is True
        assert any("negative" in w.lower() for w in result.warnings)

    def test_to_dict_structure(self):
        result = compute_cash_sweep(
            year_label="2025FY",
            opening_cash=100.0,
            cfo=50.0,
            capex_positive=20.0,
            dividends_paid=10.0,
        )
        d = result.to_dict()
        required_keys = {
            "year_label", "opening_cash", "cfo", "capex", "dividends_paid",
            "new_debt", "debt_repaid", "equity_issuance", "delta_st_investments",
            "other", "computed_ending_cash", "reported_ending_cash",
            "reconciles", "warnings",
        }
        assert required_keys.issubset(d.keys())

    def test_custom_tolerance(self):
        """Custom tight tolerance (1%) should fail where 5% passes."""
        result_5pct = compute_cash_sweep(
            year_label="2025FY",
            opening_cash=100.0,
            cfo=80.0,
            capex_positive=30.0,
            dividends_paid=20.0,
            reported_ending_cash=133.0,  # gap = 3/133 ≈ 2.3%
            tolerance=0.05,
        )
        result_1pct = compute_cash_sweep(
            year_label="2025FY",
            opening_cash=100.0,
            cfo=80.0,
            capex_positive=30.0,
            dividends_paid=20.0,
            reported_ending_cash=133.0,
            tolerance=0.01,
        )
        assert result_5pct.reconciles is True
        assert result_1pct.reconciles is False


# ---------------------------------------------------------------------------
# check_equity_roll_forward
# ---------------------------------------------------------------------------


class TestCheckEquityRollForward:
    def test_normal_case_reconciles(self):
        """Standard profitable year with dividends paid."""
        result = check_equity_roll_forward(
            year_label="2025FY",
            opening_equity=1000.0,
            net_income=150.0,
            dividends_paid=50.0,
            reported_ending_equity=1100.0,
        )
        # 1000 + 150 - 50 = 1100
        assert isinstance(result, EquityRollForwardResult)
        assert result.computed_ending_equity == pytest.approx(1100.0)
        assert result.reconciles is True
        assert result.dividends_deducted is True
        assert result.warnings == []

    def test_reconciliation_fails_large_gap(self):
        """Computed equity far from reported should fail reconciliation."""
        result = check_equity_roll_forward(
            year_label="2025FY",
            opening_equity=1000.0,
            net_income=150.0,
            dividends_paid=50.0,
            reported_ending_equity=1200.0,  # computed = 1100, gap = 100 > 5 bn tolerance
        )
        assert result.reconciles is False
        assert len(result.warnings) >= 1
        assert "reconcile" in result.warnings[0].lower()

    def test_reconciliation_within_tolerance(self):
        """Small difference within 5 VND bn absolute tolerance."""
        result = check_equity_roll_forward(
            year_label="2025FY",
            opening_equity=1000.0,
            net_income=150.0,
            dividends_paid=50.0,
            reported_ending_equity=1103.0,  # gap = 3 bn < 5 bn tolerance
        )
        assert result.reconciles is True

    def test_no_dividends_warns(self):
        """dividends_paid=0 should trigger a warning about potential omission."""
        result = check_equity_roll_forward(
            year_label="2025FY",
            opening_equity=1000.0,
            net_income=150.0,
            dividends_paid=0.0,
        )
        assert result.dividends_deducted is False
        assert len(result.warnings) >= 1
        assert any("dividend" in w.lower() for w in result.warnings)

    def test_dividends_deducted_flag_true_when_paid(self):
        result = check_equity_roll_forward(
            year_label="2025FY",
            opening_equity=1000.0,
            net_income=100.0,
            dividends_paid=30.0,
        )
        assert result.dividends_deducted is True

    def test_equity_issuance_adds_to_equity(self):
        result = check_equity_roll_forward(
            year_label="2025FY",
            opening_equity=1000.0,
            net_income=100.0,
            dividends_paid=0.0,
            equity_issuance=200.0,
            reported_ending_equity=1300.0,
        )
        assert result.computed_ending_equity == pytest.approx(1300.0)
        assert result.reconciles is True

    def test_buybacks_reduce_equity(self):
        result = check_equity_roll_forward(
            year_label="2025FY",
            opening_equity=1000.0,
            net_income=100.0,
            dividends_paid=0.0,
            buybacks=50.0,
            reported_ending_equity=1050.0,
        )
        assert result.computed_ending_equity == pytest.approx(1050.0)
        assert result.reconciles is True

    def test_oci_affects_equity(self):
        result = check_equity_roll_forward(
            year_label="2025FY",
            opening_equity=1000.0,
            net_income=100.0,
            dividends_paid=30.0,
            oci=-10.0,
            reported_ending_equity=1060.0,
        )
        # 1000 + 100 - 30 - 10 = 1060
        assert result.computed_ending_equity == pytest.approx(1060.0)
        assert result.reconciles is True

    def test_negative_dividends_auto_converted(self):
        """Negative dividends_paid should be corrected with warning."""
        result = check_equity_roll_forward(
            year_label="2025FY",
            opening_equity=1000.0,
            net_income=150.0,
            dividends_paid=-50.0,
            reported_ending_equity=1100.0,
        )
        assert result.dividends_paid == pytest.approx(50.0)
        assert result.computed_ending_equity == pytest.approx(1100.0)
        assert result.reconciles is True
        assert any("negative" in w.lower() for w in result.warnings)

    def test_no_reported_equity_reconciles_true(self):
        result = check_equity_roll_forward(
            year_label="2025FY",
            opening_equity=1000.0,
            net_income=100.0,
            dividends_paid=50.0,
        )
        assert result.reconciles is True
        assert result.reported_ending_equity is None

    def test_to_dict_structure(self):
        result = check_equity_roll_forward(
            year_label="2025FY",
            opening_equity=1000.0,
            net_income=100.0,
            dividends_paid=30.0,
        )
        d = result.to_dict()
        required_keys = {
            "year_label", "opening_equity", "net_income", "dividends_paid",
            "equity_issuance", "buybacks", "oci", "computed_ending_equity",
            "reported_ending_equity", "reconciles", "dividends_deducted", "warnings",
        }
        assert required_keys.issubset(d.keys())


# ---------------------------------------------------------------------------
# check_debt_flow_mismatch
# ---------------------------------------------------------------------------


class TestCheckDebtFlowMismatch:
    def test_normal_case_reconciles(self):
        """Debt increased by borrowing and reduced cash; net debt change matches."""
        result = check_debt_flow_mismatch(
            year_label="2025FY",
            net_debt_opening=200.0,
            net_debt_closing=250.0,   # net debt increased by 50
            net_borrowing=80.0,       # new debt raised
            delta_cash=30.0,          # cash increased too (partly from borrowing)
            delta_st_investments=0.0,
        )
        # expected_delta = 80 - 30 - 0 = 50; actual = 50 → reconciles
        assert result["reconciles"] is True
        assert result["delta_net_debt"] == pytest.approx(50.0)
        assert result["expected_delta"] == pytest.approx(50.0)
        assert result["residual"] == pytest.approx(0.0)
        assert result["warnings"] == []

    def test_mismatch_triggers_warning(self):
        """Large unexplained gap should trigger warning."""
        result = check_debt_flow_mismatch(
            year_label="2025FY",
            net_debt_opening=200.0,
            net_debt_closing=350.0,   # delta = 150
            net_borrowing=80.0,
            delta_cash=30.0,
            # expected = 50, actual = 150 → residual = 100 >> 5 bn tolerance
        )
        assert result["reconciles"] is False
        assert len(result["warnings"]) >= 1
        assert "mismatch" in result["warnings"][0].lower() or "debt" in result["warnings"][0].lower()

    def test_within_tolerance_reconciles(self):
        """Small residual within 5 VND bn tolerance should reconcile."""
        result = check_debt_flow_mismatch(
            year_label="2025FY",
            net_debt_opening=200.0,
            net_debt_closing=253.0,   # delta = 53
            net_borrowing=80.0,
            delta_cash=30.0,
            # expected = 50, residual = 3 < 5
        )
        assert result["reconciles"] is True

    def test_delta_st_investments_reduces_expected_net_debt_increase(self):
        """ST investments reduce net debt (more cash deployed → less net debt)."""
        result = check_debt_flow_mismatch(
            year_label="2025FY",
            net_debt_opening=200.0,
            net_debt_closing=220.0,   # delta = 20
            net_borrowing=50.0,
            delta_cash=10.0,
            delta_st_investments=20.0,
            # expected = 50 - 10 - 20 = 20; actual = 20 → reconciles
        )
        assert result["reconciles"] is True
        assert result["expected_delta"] == pytest.approx(20.0)

    def test_negative_net_debt_reduction_scenario(self):
        """Company paying down debt: net debt falls, net_borrowing is negative."""
        result = check_debt_flow_mismatch(
            year_label="2025FY",
            net_debt_opening=300.0,
            net_debt_closing=250.0,  # delta = -50
            net_borrowing=-50.0,     # net repayment
            delta_cash=0.0,
        )
        # expected = -50 - 0 - 0 = -50; actual = -50 → reconciles
        assert result["reconciles"] is True
        assert result["residual"] == pytest.approx(0.0)

    def test_custom_tolerance(self):
        """Custom tight tolerance should flag small residuals."""
        result_loose = check_debt_flow_mismatch(
            year_label="2025FY",
            net_debt_opening=200.0,
            net_debt_closing=253.0,
            net_borrowing=80.0,
            delta_cash=30.0,
            tolerance=5.0,  # residual = 3 → passes
        )
        result_tight = check_debt_flow_mismatch(
            year_label="2025FY",
            net_debt_opening=200.0,
            net_debt_closing=253.0,
            net_borrowing=80.0,
            delta_cash=30.0,
            tolerance=1.0,  # residual = 3 → fails
        )
        assert result_loose["reconciles"] is True
        assert result_tight["reconciles"] is False

    def test_return_dict_structure(self):
        result = check_debt_flow_mismatch(
            year_label="2025FY",
            net_debt_opening=200.0,
            net_debt_closing=250.0,
            net_borrowing=80.0,
            delta_cash=30.0,
        )
        required_keys = {"year_label", "reconciles", "delta_net_debt", "expected_delta", "residual", "warnings"}
        assert required_keys.issubset(result.keys())
        assert result["year_label"] == "2025FY"

    def test_warning_mentions_key_figures(self):
        """Warning message should be informative enough to aid diagnosis."""
        result = check_debt_flow_mismatch(
            year_label="2025FY",
            net_debt_opening=200.0,
            net_debt_closing=400.0,
            net_borrowing=50.0,
            delta_cash=0.0,
        )
        assert not result["reconciles"]
        warning = result["warnings"][0]
        # Warning should mention net_borrowing or delta or residual
        assert any(term in warning for term in ["borrowing", "residual", "mismatch", "Net_Debt", "net_borrowing"])
