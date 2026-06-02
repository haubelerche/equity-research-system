"""Tests for CAPEX sign convention in FCFF/FCFE engines (P0-04).

Convention: CAPEX is stored and displayed as positive outflow.
Formula: FCFF = NOPAT + D&A - CAPEX - ΔNWC  (CAPEX is positive → subtracted)
"""
from __future__ import annotations

import pytest
from backend.analytics.forecasting import ForecastArtifact, ForecastYear, ForecastAssumptions, run_forecast
from backend.analytics.fcff import compute_fcff, WACCAssumptions, FCFFResult
from backend.analytics.fcfe import compute_fcfe, CostOfEquityAssumptions, FCFEResult


def _make_forecast_with_capex(capex_cfs: float = -50.0) -> ForecastArtifact:
    """ForecastYear stores CAPEX as negative (CFS convention)."""
    fy = ForecastYear(
        year=2026, label="2026F",
        revenue=1000.0, cogs=-600.0, gross_profit=400.0, gross_margin=0.40,
        sga=-200.0, ebit=200.0, ebit_margin=0.20,
        depreciation=40.0, ebitda=240.0,
        interest_expense=-10.0, profit_before_tax=190.0,
        tax_expense=-19.0, net_income=171.0, net_margin=0.171,
        capex=capex_cfs,  # stored negative (CFS convention in ForecastYear)
        total_assets=1500.0, equity=1200.0, total_debt=100.0,
        other_liabilities=200.0, eps=8000.0, bvps=60000.0,
    )
    return ForecastArtifact(
        ticker="TEST", historical_periods=["2024FY"],
        forecast_periods=["2026F"],
        assumptions=ForecastAssumptions(),
        revenue_cagr=0.10, drivers={},
        forecast_years=[fy],
    )


_FACT_TABLE: dict = {
    "total_debt.ending": {"2024FY": 100.0},
    "cash_and_equivalents.ending": {"2024FY": 50.0},
    "equity.parent": {"2024FY": 1200.0},
}
_FACT_TABLE_WITH_SHARES: dict = {
    **_FACT_TABLE,
    "shares_outstanding.ending": {"2024FY": 20_000_000.0},
}


class TestFCFFCapexConvention:
    def test_fcff_year_capex_is_positive(self):
        forecast = _make_forecast_with_capex(capex_cfs=-50.0)
        result = compute_fcff("TEST", forecast, _FACT_TABLE)
        fy = result.forecast_years[0]
        # CAPEX must be stored as positive outflow
        assert fy.capex is not None
        assert fy.capex > 0, f"Expected positive CAPEX, got {fy.capex}"
        assert fy.capex == pytest.approx(50.0)

    def test_fcff_formula_correct_with_positive_capex(self):
        """FCFF = EBIT(1-T) + D&A - CAPEX - ΔNWC with positive CAPEX."""
        forecast = _make_forecast_with_capex(capex_cfs=-50.0)
        wacc_asm = WACCAssumptions(tax_rate=0.20, wacc_override=0.10)
        result = compute_fcff("TEST", forecast, _FACT_TABLE, wacc_assumptions=wacc_asm)
        fy = result.forecast_years[0]
        # EBIT=200, tax=0.20 → EBIT(1-T)=160; D&A=40; CAPEX=50; ΔNWC≈0 (first year approx)
        # Expected FCFF ≈ 160 + 40 - 50 - delta_nwc
        assert fy.fcff is not None
        expected = (fy.ebit_after_tax or 0) + (fy.depreciation or 0) - (fy.capex or 0) - (fy.delta_nwc or 0)
        assert fy.fcff == pytest.approx(expected, rel=1e-6)

    def test_to_dict_includes_capex_convention_note(self):
        forecast = _make_forecast_with_capex()
        result = compute_fcff("TEST", forecast, _FACT_TABLE)
        d = result.to_dict()
        assert d.get("capex_convention") == "positive_outflow"
        assert "capex_formula_note" in d

    def test_target_price_blocked_without_explicit_shares(self):
        forecast = _make_forecast_with_capex()
        result = compute_fcff("TEST", forecast, _FACT_TABLE)
        assert result.target_price_vnd is None
        assert any("shares_outstanding" in w for w in result.warnings)

    def test_target_price_uses_explicit_shares(self):
        forecast = _make_forecast_with_capex()
        result = compute_fcff("TEST", forecast, _FACT_TABLE_WITH_SHARES)
        assert result.shares_mn == pytest.approx(20.0)
        assert result.target_price_vnd is not None

    def test_negative_input_capex_gives_same_fcff_as_positive_input(self):
        """Whether ForecastYear.capex = -50 or +50, FCFFYear CAPEX and FCFF value must be equal."""
        f1 = _make_forecast_with_capex(capex_cfs=-50.0)
        f2 = _make_forecast_with_capex(capex_cfs=50.0)  # source stored as positive
        r1 = compute_fcff("TEST", f1, _FACT_TABLE, wacc_assumptions=WACCAssumptions(wacc_override=0.10))
        r2 = compute_fcff("TEST", f2, _FACT_TABLE, wacc_assumptions=WACCAssumptions(wacc_override=0.10))
        assert r1.forecast_years[0].capex == r2.forecast_years[0].capex
        assert r1.forecast_years[0].fcff == pytest.approx(r2.forecast_years[0].fcff or 0, rel=1e-6)


class TestFCFECapexConvention:
    def test_fcfe_year_capex_is_positive(self):
        forecast = _make_forecast_with_capex(capex_cfs=-50.0)
        result = compute_fcfe("TEST", forecast, _FACT_TABLE)
        fy = result.forecast_years[0]
        assert fy.capex is not None
        assert fy.capex > 0, f"Expected positive CAPEX, got {fy.capex}"
        assert fy.capex == pytest.approx(50.0)

    def test_fcfe_formula_correct_with_positive_capex(self):
        """FCFE = NI + D&A - CAPEX - ΔNWC + NB with positive CAPEX."""
        forecast = _make_forecast_with_capex(capex_cfs=-50.0)
        result = compute_fcfe("TEST", forecast, _FACT_TABLE)
        fy = result.forecast_years[0]
        assert fy.fcfe is not None
        expected = (fy.net_income or 0) + (fy.depreciation or 0) - (fy.capex or 0) - (fy.delta_nwc or 0) + (fy.net_borrowing or 0)
        assert fy.fcfe == pytest.approx(expected, rel=1e-6)

    def test_to_dict_includes_capex_convention_note(self):
        forecast = _make_forecast_with_capex()
        result = compute_fcfe("TEST", forecast, _FACT_TABLE)
        d = result.to_dict()
        assert d.get("capex_convention") == "positive_outflow"
        assert "capex_formula_note" in d

    def test_target_price_blocked_without_explicit_shares(self):
        forecast = _make_forecast_with_capex()
        result = compute_fcfe("TEST", forecast, _FACT_TABLE)
        assert result.target_price_vnd is None
        assert any("shares_outstanding" in w for w in result.warnings)

    def test_target_price_uses_explicit_shares(self):
        forecast = _make_forecast_with_capex()
        result = compute_fcfe("TEST", forecast, _FACT_TABLE_WITH_SHARES)
        assert result.shares_mn == pytest.approx(20.0)
        assert result.target_price_vnd is not None
