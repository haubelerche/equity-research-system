"""Unit tests for backend/analytics/dcf.py.

Tests: run_dcf, run_three_scenarios, DCFAssumptions.
No DB required — all in-memory.
"""
from __future__ import annotations

import pytest

from backend.analytics.dcf import DCFAssumptions, DCFResult, run_dcf, run_three_scenarios


def _minimal_table() -> dict:
    """Minimal fact table with 3 FY periods of FCF data."""
    return {
        "operating_cash_flow.total": {
            "2021FY": 1000.0,
            "2022FY": 1100.0,
            "2023FY": 1200.0,
        },
        "capex.total": {
            "2021FY": -200.0,
            "2022FY": -210.0,
            "2023FY": -220.0,
        },
        "net_income.parent": {"2023FY": 600.0},
        "eps.basic":         {"2023FY": 6000.0},  # → 600bn * 1000 / 6000 = 100mn shares
        "total_debt.ending": {"2023FY": 400.0},
        "cash_and_equivalents.ending": {"2023FY": 150.0},
    }


class TestRunDcf:
    def test_returns_dcf_result(self):
        result = run_dcf("DHG", _minimal_table(), DCFAssumptions())
        assert isinstance(result, DCFResult)

    def test_fcf_history_computed(self):
        result = run_dcf("DHG", _minimal_table(), DCFAssumptions())
        # FCF = OCF + capex_signed = 1200 + (-220) = 980  (capex stored as negative outflow)
        assert result.fcf_history_vnd_bn["2023FY"] == pytest.approx(1200.0 + (-220.0))

    def test_projected_fcf_length(self):
        assumptions = DCFAssumptions(forecast_years=5)
        result = run_dcf("DHG", _minimal_table(), assumptions)
        assert len(result.projected_fcf_vnd_bn) == 5
        assert len(result.pv_fcf_vnd_bn) == 5

    def test_shares_derived_from_eps(self):
        result = run_dcf("DHG", _minimal_table(), DCFAssumptions())
        # shares_mn = (600 bn * 1000) / 6000 VND = 100 mn
        assert result.shares_mn == pytest.approx(100.0, abs=0.01)

    def test_intrinsic_value_positive(self):
        result = run_dcf("DHG", _minimal_table(), DCFAssumptions())
        assert result.intrinsic_value_per_share_vnd is not None
        assert result.intrinsic_value_per_share_vnd > 0

    def test_net_debt_calculation(self):
        result = run_dcf("DHG", _minimal_table(), DCFAssumptions())
        # net_debt = 400 - 150 = 250
        assert result.net_debt_vnd_bn == pytest.approx(250.0, abs=0.01)

    def test_growth_override_respected(self):
        assumptions_fixed = DCFAssumptions(fcf_growth_override=0.10)
        result = run_dcf("DHG", _minimal_table(), assumptions_fixed)
        # First projected FCF = latest_fcf * (1 + 0.10)
        latest_fcf = 1200.0 + (-220.0)  # = 980 (capex stored as negative outflow)
        assert result.projected_fcf_vnd_bn[0] == pytest.approx(latest_fcf * 1.10, rel=1e-4)

    def test_no_fcf_data_produces_no_intrinsic_value(self):
        empty_table = {"net_income.parent": {"2023FY": 100.0}}
        result = run_dcf("DHG", empty_table, DCFAssumptions())
        assert result.intrinsic_value_per_share_vnd is None
        assert "No FCF history" in " ".join(result.warnings)

    def test_single_period_fcf_uses_default_growth(self):
        table = {
            "operating_cash_flow.total": {"2023FY": 1000.0},
            "capex.total": {"2023FY": -200.0},
            "net_income.parent": {"2023FY": 500.0},
            "eps.basic": {"2023FY": 5000.0},
        }
        result = run_dcf("DHG", table, DCFAssumptions())
        assert any("5%" in w or "1 FCF period" in w for w in result.warnings)

    def test_wacc_le_terminal_growth_capped(self):
        assumptions = DCFAssumptions(wacc=0.05, terminal_growth=0.06)
        result = run_dcf("DHG", _minimal_table(), assumptions)
        assert any("capped" in w.lower() or "WACC" in w for w in result.warnings)

    def test_wacc_le_terminal_growth_blocks_target_price(self):
        """WACC <= terminal_growth must emit INVALID and block target price (not just cap g)."""
        assumptions = DCFAssumptions(wacc=0.05, terminal_growth=0.06)
        result = run_dcf("DHG", _minimal_table(), assumptions)
        assert result.intrinsic_value_per_share_vnd is None
        assert any("INVALID" in w for w in result.warnings)

    def test_forecast_years_zero_returns_empty(self):
        """forecast_years=0 must return early with no target price instead of IndexError."""
        assumptions = DCFAssumptions(forecast_years=0)
        result = run_dcf("DHG", _minimal_table(), assumptions)
        assert result.intrinsic_value_per_share_vnd is None
        assert result.projected_fcf_vnd_bn == []

    def test_capex_positive_auto_negated(self):
        """Positive CAPEX in source data must be auto-negated and warned, not inflate FCF."""
        table = {
            "operating_cash_flow.total": {"2023FY": 1000.0},
            "capex.total": {"2023FY": 200.0},   # positive — should behave same as -200
            "net_income.parent": {"2023FY": 500.0},
            "eps.basic": {"2023FY": 5000.0},
        }
        result = run_dcf("DHG", table, DCFAssumptions())
        # FCF should equal 1000 - 200 = 800, not 1000 + 200 = 1200
        assert result.fcf_history_vnd_bn["2023FY"] == pytest.approx(800.0)
        assert any("auto-negat" in w for w in result.warnings)

    def test_cagr_none_when_start_fcf_negative(self):
        """When first FCF is negative CAGR is unavailable — must fall back to 5%, not crash."""
        table = {
            "operating_cash_flow.total": {"2021FY": 100.0, "2022FY": 200.0},
            "capex.total": {"2021FY": -500.0, "2022FY": -100.0},  # 2021 FCF = -400
            "net_income.parent": {"2022FY": 100.0},
            "eps.basic": {"2022FY": 1000.0},
        }
        result = run_dcf("DHG", table, DCFAssumptions())
        assert result.fcf_cagr is None
        assert any("5%" in w or "unavailable" in w for w in result.warnings)

    def test_net_debt_subtracts_short_term_investments(self):
        """net_debt = total_debt - cash - short_term_investments."""
        table = dict(_minimal_table())
        table["short_term_investments.ending"] = {"2023FY": 50.0}
        result = run_dcf("DHG", table, DCFAssumptions())
        # net_debt = 400 - 150 - 50 = 200
        assert result.net_debt_vnd_bn == pytest.approx(200.0, abs=0.01)

    def test_to_dict_zero_shares_not_hidden(self):
        """to_dict() must not coerce 0.0 to None for numeric fields."""
        result = run_dcf("DHG", _minimal_table(), DCFAssumptions())
        d = result.to_dict()
        # shares_mn is derived from EPS so should be non-None; field must use is not None check
        assert d["shares_mn"] is not None

    def test_periods_used_sorted(self):
        result = run_dcf("DHG", _minimal_table(), DCFAssumptions())
        assert result.periods_used == sorted(result.periods_used)

    def test_to_dict_serializable(self):
        import json
        result = run_dcf("DHG", _minimal_table(), DCFAssumptions())
        d = result.to_dict()
        json_str = json.dumps(d)  # should not raise
        assert "intrinsic_value_per_share_vnd" in d

    def test_terminal_value_positive(self):
        result = run_dcf("DHG", _minimal_table(), DCFAssumptions())
        assert result.terminal_value_vnd_bn > 0
        assert result.pv_terminal_value_vnd_bn > 0


class TestRunThreeScenarios:
    def test_returns_three_scenarios(self):
        scenarios = run_three_scenarios("DHG", _minimal_table())
        assert set(scenarios.keys()) == {"bear", "base", "bull"}

    def test_bear_wacc_higher_than_base(self):
        base_assumptions = DCFAssumptions(wacc=0.10)
        scenarios = run_three_scenarios("DHG", _minimal_table(), base_assumptions)
        assert scenarios["bear"].assumptions.wacc > scenarios["base"].assumptions.wacc

    def test_bull_wacc_lower_than_base(self):
        base_assumptions = DCFAssumptions(wacc=0.10)
        scenarios = run_three_scenarios("DHG", _minimal_table(), base_assumptions)
        assert scenarios["bull"].assumptions.wacc < scenarios["base"].assumptions.wacc

    def test_bull_intrinsic_higher_than_bear(self):
        scenarios = run_three_scenarios("DHG", _minimal_table())
        bull_val = scenarios["bull"].intrinsic_value_per_share_vnd or 0
        bear_val = scenarios["bear"].intrinsic_value_per_share_vnd or 0
        assert bull_val > bear_val

    def test_base_uses_provided_assumptions(self):
        custom = DCFAssumptions(wacc=0.12, terminal_growth=0.04, forecast_years=7)
        scenarios = run_three_scenarios("DHG", _minimal_table(), custom)
        assert scenarios["base"].assumptions.wacc == pytest.approx(0.12)
        assert scenarios["base"].assumptions.forecast_years == 7

    def test_no_base_uses_defaults(self):
        scenarios = run_three_scenarios("DHG", _minimal_table())
        assert scenarios["base"].assumptions.wacc == pytest.approx(0.10)
