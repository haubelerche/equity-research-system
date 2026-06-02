"""Unit tests for backend/evaluation/numeric_consistency.py"""
import pytest
from backend.evaluation.numeric_consistency import (
    check_capex_non_negative,
    check_net_debt_formula,
    check_terminal_value_in_ev,
    check_equity_roll_forward_dividends,
    check_sensitivity_grid_varies,
    check_discount_rate_exceeds_growth,
    run_numeric_consistency_gate,
)


# ── check_capex_non_negative ───────────────────────────────────────────────────

class TestCapexNonNegative:
    def test_all_positive_passes(self):
        r = check_capex_non_negative({"2022": 100.0, "2023": 150.0, "2024": 200.0})
        assert r["passed"] is True
        assert r["status"] == "pass"
        assert r["blocking_reasons"] == []

    def test_zero_passes(self):
        r = check_capex_non_negative({"2022": 0.0})
        assert r["passed"] is True

    def test_negative_fails(self):
        r = check_capex_non_negative({"2022": 100.0, "2023": -50.0})
        assert r["passed"] is False
        assert r["status"] == "fail"
        assert any("2023" in msg for msg in r["blocking_reasons"])

    def test_multiple_negatives_all_reported(self):
        r = check_capex_non_negative({"2021": -10.0, "2022": -20.0, "2023": 30.0})
        assert r["passed"] is False
        assert len(r["blocking_reasons"]) == 2

    def test_empty_series_passes(self):
        r = check_capex_non_negative({})
        assert r["passed"] is True


# ── check_net_debt_formula ─────────────────────────────────────────────────────

class TestNetDebtFormula:
    def test_matching_values_passes(self):
        r = check_net_debt_formula(
            interest_bearing_debt=500.0, cash=100.0, st_investments=50.0,
            reported_net_debt=350.0
        )
        assert r["passed"] is True

    def test_none_reported_skips(self):
        r = check_net_debt_formula(
            interest_bearing_debt=500.0, cash=100.0, st_investments=50.0,
            reported_net_debt=None
        )
        assert r["passed"] is True
        assert "skipped" in r["summary"]["note"]

    def test_mismatch_beyond_tolerance_fails(self):
        # expected = 500 - 100 - 50 = 350; reported = 400 (diff=50 > tol=5)
        r = check_net_debt_formula(
            interest_bearing_debt=500.0, cash=100.0, st_investments=50.0,
            reported_net_debt=400.0, tolerance=5.0
        )
        assert r["passed"] is False
        assert "mismatch" in r["blocking_reasons"][0]

    def test_within_tolerance_passes(self):
        # expected = 350; reported = 353 (diff=3 <= tol=5)
        r = check_net_debt_formula(
            interest_bearing_debt=500.0, cash=100.0, st_investments=50.0,
            reported_net_debt=353.0, tolerance=5.0
        )
        assert r["passed"] is True

    def test_negative_net_debt_valid_if_formula_matches(self):
        # company has more cash than debt
        r = check_net_debt_formula(
            interest_bearing_debt=100.0, cash=300.0, st_investments=50.0,
            reported_net_debt=-250.0
        )
        assert r["passed"] is True


# ── check_terminal_value_in_ev ─────────────────────────────────────────────────

class TestTerminalValueInEv:
    def test_valid_tv_passes(self):
        r = check_terminal_value_in_ev(pv_terminal_value=800.0, enterprise_value=1000.0)
        assert r["passed"] is True

    def test_none_tv_fails(self):
        r = check_terminal_value_in_ev(pv_terminal_value=None, enterprise_value=1000.0)
        assert r["passed"] is False
        assert "None" in r["blocking_reasons"][0]

    def test_zero_tv_fails(self):
        r = check_terminal_value_in_ev(pv_terminal_value=0, enterprise_value=1000.0)
        assert r["passed"] is False

    def test_tv_equals_ev_fails(self):
        # Means FCF PV was never added
        r = check_terminal_value_in_ev(pv_terminal_value=1000.0, enterprise_value=1000.0)
        assert r["passed"] is False

    def test_none_ev_with_valid_tv_passes(self):
        r = check_terminal_value_in_ev(pv_terminal_value=800.0, enterprise_value=None)
        assert r["passed"] is True

    def test_both_none_fails(self):
        r = check_terminal_value_in_ev(pv_terminal_value=None, enterprise_value=None)
        assert r["passed"] is False


# ── check_equity_roll_forward_dividends ───────────────────────────────────────

class TestEquityRollForward:
    def _build(self, *, eq_prev=1000.0, ni=200.0, div=50.0, eq_curr=1150.0):
        return (
            {"2022": eq_prev, "2023": eq_curr},
            {"2023": ni},
            {"2023": div},
        )

    def test_exact_match_passes(self):
        eq, ni, div = self._build(eq_curr=1150.0)  # 1000+200-50=1150
        r = check_equity_roll_forward_dividends(eq, ni, div)
        assert r["passed"] is True

    def test_within_tolerance_passes(self):
        eq, ni, div = self._build(eq_curr=1155.0)  # diff=5 <= tol=10
        r = check_equity_roll_forward_dividends(eq, ni, div, tolerance=10.0)
        assert r["passed"] is True

    def test_beyond_tolerance_fails(self):
        eq, ni, div = self._build(eq_curr=1200.0)  # diff=50 > tol=10
        r = check_equity_roll_forward_dividends(eq, ni, div, tolerance=10.0)
        assert r["passed"] is False
        assert "2023" in r["blocking_reasons"][0]

    def test_empty_forecasts_passes(self):
        r = check_equity_roll_forward_dividends({}, {}, {})
        assert r["passed"] is True

    def test_single_year_no_pairs_passes(self):
        r = check_equity_roll_forward_dividends({"2022": 1000.0}, {}, {})
        assert r["passed"] is True

    def test_missing_value_skips_period(self):
        # ni for 2023 is missing → skip that pair
        r = check_equity_roll_forward_dividends(
            {"2022": 1000.0, "2023": 1200.0},
            {},           # no ni
            {"2023": 50.0},
        )
        assert r["passed"] is True
        assert r["summary"]["checked_periods"] == 0


# ── check_sensitivity_grid_varies ─────────────────────────────────────────────

class TestSensitivityGridVaries:
    def test_varied_values_pass(self):
        matrix = {
            "wacc_low": {"tg_low": 10.0, "tg_high": 12.0},
            "wacc_high": {"tg_low": 8.0, "tg_high": 9.5},
        }
        r = check_sensitivity_grid_varies(matrix)
        assert r["passed"] is True

    def test_all_identical_fails(self):
        matrix = {
            "wacc_low": {"tg_low": 10.0, "tg_high": 10.0},
            "wacc_high": {"tg_low": 10.0, "tg_high": 10.0},
        }
        r = check_sensitivity_grid_varies(matrix)
        assert r["passed"] is False
        assert "absolute reference" in r["blocking_reasons"][0]

    def test_empty_matrix_fails(self):
        r = check_sensitivity_grid_varies({})
        assert r["passed"] is False

    def test_all_none_fails(self):
        matrix = {"r1": {"c1": None, "c2": None}}
        r = check_sensitivity_grid_varies(matrix)
        assert r["passed"] is False

    def test_single_non_none_value_fails(self):
        matrix = {"r1": {"c1": 10.0, "c2": None}}
        r = check_sensitivity_grid_varies(matrix)
        assert r["passed"] is False  # only 1 distinct value

    def test_two_distinct_values_passes(self):
        matrix = {"r1": {"c1": 10.0, "c2": 11.0}}
        r = check_sensitivity_grid_varies(matrix)
        assert r["passed"] is True


# ── check_discount_rate_exceeds_growth ────────────────────────────────────────

class TestDiscountRateExceedsGrowth:
    def test_wacc_above_growth_passes(self):
        r = check_discount_rate_exceeds_growth(wacc=0.12, re=0.14, terminal_growth=0.03)
        assert r["passed"] is True

    def test_wacc_equals_growth_fails(self):
        r = check_discount_rate_exceeds_growth(wacc=0.03, re=0.14, terminal_growth=0.03)
        assert r["passed"] is False
        assert any("WACC" in msg for msg in r["blocking_reasons"])

    def test_wacc_below_growth_fails(self):
        r = check_discount_rate_exceeds_growth(wacc=0.02, re=0.14, terminal_growth=0.03)
        assert r["passed"] is False

    def test_re_below_growth_fails(self):
        r = check_discount_rate_exceeds_growth(wacc=0.12, re=0.02, terminal_growth=0.03)
        assert r["passed"] is False
        assert any("Re" in msg for msg in r["blocking_reasons"])

    def test_both_none_passes_no_check(self):
        r = check_discount_rate_exceeds_growth(wacc=None, re=None, terminal_growth=0.03)
        assert r["passed"] is True
        assert r["summary"]["checks_run"] == 0

    def test_only_wacc_provided(self):
        r = check_discount_rate_exceeds_growth(wacc=0.12, re=None, terminal_growth=0.03)
        assert r["passed"] is True
        assert r["summary"]["checks_run"] == 1

    def test_growth_none_skips(self):
        r = check_discount_rate_exceeds_growth(wacc=0.12, re=0.14, terminal_growth=None)
        assert r["passed"] is True
        assert r["summary"]["checks_run"] == 0


# ── run_numeric_consistency_gate ──────────────────────────────────────────────

class TestRunNumericConsistencyGate:
    def _minimal_artifact(self):
        return {
            "fcff": {
                "capex_series": {"2022": 100.0, "2023": 150.0},
                "interest_bearing_debt": 500.0,
                "cash": 100.0,
                "st_investments": 50.0,
                "net_debt": 350.0,
                "pv_terminal_value": 800.0,
                "enterprise_value": 1000.0,
                "wacc": 0.12,
                "terminal_growth": 0.03,
            },
            "fcfe": {
                "re": 0.14,
                "terminal_growth": 0.03,
            },
            "sensitivity": {
                "matrix": {
                    "wacc_low": {"tg_low": 10.0, "tg_high": 12.0},
                    "wacc_high": {"tg_low": 8.0, "tg_high": 9.5},
                }
            },
            "equity_forecast": {"2022": 1000.0, "2023": 1150.0},
            "net_income_forecast": {"2023": 200.0},
            "dividends_forecast": {"2023": 50.0},
        }

    def test_all_valid_passes(self):
        r = run_numeric_consistency_gate(self._minimal_artifact())
        assert r["passed"] is True
        assert r["status"] == "pass"
        assert r["summary"]["checks_failed"] == 0

    def test_empty_artifact_passes(self):
        r = run_numeric_consistency_gate({})
        assert r["passed"] is True
        assert r["summary"]["checks_run"] == 0

    def test_negative_capex_fails(self):
        artifact = self._minimal_artifact()
        artifact["fcff"]["capex_series"]["2023"] = -50.0
        r = run_numeric_consistency_gate(artifact)
        assert r["passed"] is False
        assert any("capex" in msg.lower() for msg in r["blocking_reasons"])

    def test_wacc_below_growth_fails(self):
        artifact = self._minimal_artifact()
        artifact["fcff"]["wacc"] = 0.02  # below terminal_growth=0.03
        r = run_numeric_consistency_gate(artifact)
        assert r["passed"] is False

    def test_sensitivity_all_identical_fails(self):
        artifact = self._minimal_artifact()
        artifact["sensitivity"]["matrix"] = {
            "r1": {"c1": 10.0, "c2": 10.0},
            "r2": {"c1": 10.0, "c2": 10.0},
        }
        r = run_numeric_consistency_gate(artifact)
        assert r["passed"] is False

    def test_summary_counts_correct(self):
        artifact = self._minimal_artifact()
        r = run_numeric_consistency_gate(artifact)
        assert r["summary"]["checks_run"] >= 4
        assert r["summary"]["checks_passed"] == r["summary"]["checks_run"]
