"""Tests for backend.analytics.tax_policy — unified TaxPolicy module (P0-01)."""
from __future__ import annotations

import pytest
from backend.analytics.tax_policy import TaxPolicy, build_tax_policy
from backend.analytics.forecasting import run_forecast, ForecastAssumptions
from backend.analytics.fcff import compute_fcff, WACCAssumptions


def _make_fact_table(years: list[str], pbt_vals: list[float], ni_vals: list[float]) -> dict:
    table: dict = {"profit_before_tax.total": {}, "net_income.parent": {}}
    for y, pbt, ni in zip(years, pbt_vals, ni_vals):
        table["profit_before_tax.total"][y] = pbt
        table["net_income.parent"][y] = ni
    return table


class TestBuildTaxPolicyFromValidData:
    def test_valid_rates_use_median(self):
        # 3 years: rates 0.10, 0.12, 0.15 → median = 0.12
        ft = _make_fact_table(
            ["2022FY", "2023FY", "2024FY"],
            [100.0, 100.0, 100.0],
            [90.0, 88.0, 85.0],
        )
        tp = build_tax_policy("TEST", ft, ["2022FY", "2023FY", "2024FY"])
        assert tp.source == "historical_effective_tax_rate"
        assert abs(tp.effective_tax_rate - 0.12) < 1e-6
        assert len(tp.historical_observations) == 3
        assert len(tp.excluded_observations) == 0

    def test_confidence_is_medium_for_historical_data(self):
        ft = _make_fact_table(["2023FY"], [100.0], [88.0])
        tp = build_tax_policy("TEST", ft, ["2023FY"])
        assert tp.confidence == "medium"


class TestExclusionFilters:
    def test_negative_pbt_excluded(self):
        ft = _make_fact_table(["2022FY", "2023FY"], [-50.0, 100.0], [-40.0, 88.0])
        tp = build_tax_policy("TEST", ft, ["2022FY", "2023FY"])
        assert len(tp.excluded_observations) == 1
        assert tp.excluded_observations[0]["period"] == "2022FY"
        assert "pbt" in tp.excluded_observations[0]["reason"] or "loss" in tp.excluded_observations[0]["reason"]

    def test_negative_tax_expense_excluded(self):
        # ni > pbt implies negative tax (e.g. subsidy / deferred tax reversal)
        ft = _make_fact_table(["2022FY"], [100.0], [110.0])
        tp = build_tax_policy("TEST", ft, ["2022FY"])
        assert len(tp.excluded_observations) == 1
        assert tp.excluded_observations[0]["period"] == "2022FY"

    def test_rate_above_35pct_excluded(self):
        # tax_expense = 40, pbt = 100 → rate = 0.40 > 0.35
        ft = _make_fact_table(["2022FY"], [100.0], [60.0])
        tp = build_tax_policy("TEST", ft, ["2022FY"])
        assert len(tp.excluded_observations) == 1

    def test_missing_pbt_excluded(self):
        ft: dict = {"net_income.parent": {"2022FY": 88.0}}
        tp = build_tax_policy("TEST", ft, ["2022FY"])
        assert len(tp.excluded_observations) == 1


class TestFallbackToStatutory:
    def test_no_valid_data_falls_back_to_20pct(self):
        # All years have negative PBT
        ft = _make_fact_table(["2022FY", "2023FY"], [-100.0, -50.0], [-90.0, -40.0])
        tp = build_tax_policy("TEST", ft, ["2022FY", "2023FY"])
        assert tp.source == "statutory_default"
        assert tp.effective_tax_rate == 0.20
        assert tp.confidence == "low"
        assert tp.fallback_reason is not None

    def test_empty_fact_table_falls_back_to_20pct(self):
        tp = build_tax_policy("TEST", {}, [])
        assert tp.source == "statutory_default"
        assert tp.effective_tax_rate == 0.20
        assert tp.confidence == "low"


class TestManualOverride:
    def test_manual_override_sets_correct_source_and_rate(self):
        tp = build_tax_policy("TEST", {}, [], manual_override=0.15)
        assert tp.source == "manual_override"
        assert tp.effective_tax_rate == 0.15
        assert tp.confidence == "high"

    def test_manual_override_ignores_historical_data(self):
        ft = _make_fact_table(["2023FY"], [100.0], [88.0])
        tp = build_tax_policy("TEST", ft, ["2023FY"], manual_override=0.25)
        assert tp.effective_tax_rate == 0.25


class TestForecastUsesToAxPolicy:
    def _make_full_fact_table(self) -> dict:
        """Minimal fact table with enough data for run_forecast to compute tax_policy."""
        ft: dict = {
            "revenue.net": {"2022FY": 1000.0, "2023FY": 1100.0, "2024FY": 1200.0},
            "gross_profit.total": {"2022FY": 400.0, "2023FY": 440.0, "2024FY": 480.0},
            "sga.total": {"2022FY": -200.0, "2023FY": -210.0, "2024FY": -220.0},
            "depreciation.total": {"2022FY": 30.0, "2023FY": 32.0, "2024FY": 34.0},
            "capex.total": {"2022FY": -50.0, "2023FY": -55.0, "2024FY": -60.0},
            "interest_expense.total": {"2022FY": -10.0, "2023FY": -11.0, "2024FY": -12.0},
            "profit_before_tax.total": {"2022FY": 190.0, "2023FY": 219.0, "2024FY": 248.0},
            "net_income.parent": {"2022FY": 171.0, "2023FY": 197.1, "2024FY": 223.2},  # ~10% tax
            "total_assets.ending": {"2024FY": 2000.0},
            "equity.parent": {"2024FY": 1500.0},
            "total_debt.ending": {"2024FY": 100.0},
            "eps.basic": {"2024FY": 8000.0},
        }
        return ft

    def test_forecast_artifact_contains_tax_policy(self):
        ft = self._make_full_fact_table()
        result = run_forecast("TEST", ft)
        assert result.tax_policy is not None
        assert result.tax_policy.source == "historical_effective_tax_rate"

    def test_forecast_tax_rate_matches_tax_policy(self):
        """Tax rate used in P&L must equal TaxPolicy.effective_tax_rate."""
        ft = self._make_full_fact_table()
        result = run_forecast("TEST", ft)
        tp = result.tax_policy
        # Re-derive tax used in forecast from first year P&L
        fy1 = result.forecast_years[0]
        if fy1.profit_before_tax and fy1.tax_expense is not None:
            derived_rate = abs(fy1.tax_expense) / fy1.profit_before_tax
            assert abs(derived_rate - tp.effective_tax_rate) < 0.001


class TestFCFFUsesTaxPolicy:
    def _make_minimal_forecast(self):
        from backend.analytics.forecasting import ForecastArtifact, ForecastYear, ForecastAssumptions
        from backend.analytics.tax_policy import TaxPolicy
        tp = TaxPolicy(
            ticker="TEST", valuation_year=2025,
            effective_tax_rate=0.10,
            source="historical_effective_tax_rate", confidence="medium",
        )
        fy = ForecastYear(
            year=2026, label="2026F",
            revenue=1200.0, cogs=-720.0, gross_profit=480.0, gross_margin=0.40,
            sga=-240.0, ebit=240.0, ebit_margin=0.20,
            depreciation=40.0, ebitda=280.0,
            interest_expense=-12.0, profit_before_tax=228.0,
            tax_expense=-22.8, net_income=205.2, net_margin=0.171,
            capex=-36.0,
            total_assets=2100.0, equity=1600.0, total_debt=100.0,
            other_liabilities=400.0, eps=9000.0, bvps=70000.0,
        )
        return ForecastArtifact(
            ticker="TEST", historical_periods=["2024FY"],
            forecast_periods=["2026F"],
            assumptions=ForecastAssumptions(),
            revenue_cagr=0.10, drivers={},
            forecast_years=[fy],
            tax_policy=tp,
        ), tp

    def test_fcff_uses_tax_policy_rate_when_provided(self):
        forecast, tp = self._make_minimal_forecast()
        fact_table: dict = {
            "total_debt.ending": {"2024FY": 100.0},
            "cash_and_equivalents.ending": {"2024FY": 200.0},
            "equity.parent": {"2024FY": 1500.0},
        }
        wacc_asm = WACCAssumptions(tax_rate=0.20, tax_policy=tp)
        result = compute_fcff("TEST", forecast, fact_table, wacc_assumptions=wacc_asm)
        # EBIT=240, tax_policy rate=0.10 → EBIT(1-T) = 240*(1-0.10) = 216
        fy = result.forecast_years[0]
        assert fy.ebit_after_tax is not None
        assert abs(fy.ebit_after_tax - 216.0) < 0.5

    def test_fcff_warns_when_no_tax_policy_provided(self):
        forecast, _ = self._make_minimal_forecast()
        fact_table: dict = {
            "total_debt.ending": {"2024FY": 100.0},
            "cash_and_equivalents.ending": {"2024FY": 200.0},
            "equity.parent": {"2024FY": 1500.0},
        }
        # No tax_policy in WACCAssumptions
        wacc_asm = WACCAssumptions(tax_rate=0.20)
        result = compute_fcff("TEST", forecast, fact_table, wacc_assumptions=wacc_asm)
        assert any("TaxPolicy" in w or "tax" in w.lower() for w in result.warnings)
