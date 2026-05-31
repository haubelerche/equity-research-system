"""Tests for backend.analytics.dividend_schedule (P1-03)."""
from __future__ import annotations

import pytest
from backend.analytics.dividend_schedule import (
    build_dividend_schedule,
    _compute_historical_payout_ratio,
)
from backend.analytics.forecasting import run_forecast, ForecastAssumptions


def _make_ft_with_dividends(periods: list[str], divs: list[float], nis: list[float]) -> dict:
    ft: dict = {
        "dividends_paid.total": {},
        "net_income.parent": {},
    }
    for p, d, ni in zip(periods, divs, nis):
        ft["dividends_paid.total"][p] = d
        ft["net_income.parent"][p] = ni
    return ft


class TestHistoricalPayoutRatio:
    def test_median_payout_computed_correctly(self):
        ft = _make_ft_with_dividends(
            ["2022FY", "2023FY", "2024FY"],
            [-60.0, -70.0, -80.0],  # CFS negative convention
            [100.0, 100.0, 100.0],
        )
        ratio = _compute_historical_payout_ratio(ft, ["2022FY", "2023FY", "2024FY"])
        assert ratio == pytest.approx(0.70)  # median of 0.60, 0.70, 0.80

    def test_returns_none_when_no_dividend_data(self):
        ft = {"net_income.parent": {"2024FY": 100.0}}
        ratio = _compute_historical_payout_ratio(ft, ["2024FY"])
        assert ratio is None

    def test_excludes_payout_above_100pct(self):
        ft = _make_ft_with_dividends(
            ["2022FY", "2023FY"],
            [-150.0, -50.0],  # 2022: 150% payout (excluded), 2023: 50%
            [100.0, 100.0],
        )
        ratio = _compute_historical_payout_ratio(ft, ["2022FY", "2023FY"])
        assert ratio == pytest.approx(0.50)


class TestBuildDividendSchedule:
    def _forecast_nis(self):
        return {"2026F": 200.0, "2027F": 210.0, "2028F": 220.0}

    def test_historical_payout_applied_to_forecast(self):
        ft = _make_ft_with_dividends(["2024FY"], [-60.0], [100.0])
        ds = build_dividend_schedule("TEST", ft, ["2024FY"], self._forecast_nis())
        assert ds.method == "historical_median_payout"
        for row in ds.forecast_rows:
            assert row.payout_ratio == pytest.approx(0.60)
            assert row.cash_dividend == pytest.approx(row.net_income * 0.60)
            assert row.retained_earnings_addition == pytest.approx(row.net_income * 0.40)

    def test_manual_payout_override(self):
        ds = build_dividend_schedule("TEST", {}, [], self._forecast_nis(), manual_payout_ratio=0.30)
        assert ds.method == "manual_override"
        assert ds.historical_payout_ratio == pytest.approx(0.30)
        for row in ds.forecast_rows:
            assert row.retained_earnings_addition == pytest.approx(row.net_income * 0.70)

    def test_missing_dividend_data_warns_and_retains_all(self):
        ds = build_dividend_schedule("TEST", {}, [], self._forecast_nis())
        assert ds.method == "missing"
        assert len(ds.warnings) > 0
        # All earnings retained when no dividend data
        for row in ds.forecast_rows:
            assert row.retained_earnings_addition == pytest.approx(row.net_income or 0)

    def test_retained_earnings_schedule_keys_match_forecast_labels(self):
        ft = _make_ft_with_dividends(["2024FY"], [-50.0], [100.0])
        ds = build_dividend_schedule("TEST", ft, ["2024FY"], self._forecast_nis())
        schedule = ds.retained_earnings_schedule()
        assert set(schedule.keys()) == {"2026F", "2027F", "2028F"}

    def test_to_dict_is_json_serializable(self):
        import json
        ds = build_dividend_schedule("TEST", {}, [], {"2026F": 200.0})
        result = json.dumps(ds.to_dict())
        assert "forecast_rows" in result


class TestForecastUsesdividendSchedule:
    def _full_ft(self) -> dict:
        return {
            "revenue.net": {"2022FY": 1000.0, "2023FY": 1100.0, "2024FY": 1200.0},
            "gross_profit.total": {"2022FY": 400.0, "2023FY": 440.0, "2024FY": 480.0},
            "sga.total": {"2022FY": -200.0, "2023FY": -210.0, "2024FY": -220.0},
            "depreciation.total": {"2022FY": 40.0, "2023FY": 42.0, "2024FY": 44.0},
            "capex.total": {"2022FY": -50.0, "2023FY": -55.0, "2024FY": -60.0},
            "interest_expense.total": {"2022FY": -5.0, "2023FY": -6.0, "2024FY": -7.0},
            "profit_before_tax.total": {"2022FY": 195.0, "2023FY": 224.0, "2024FY": 253.0},
            "net_income.parent": {"2022FY": 175.5, "2023FY": 201.6, "2024FY": 227.7},
            "dividends_paid.total": {"2022FY": -87.75, "2023FY": -100.8, "2024FY": -113.85},  # 50% payout
            "total_assets.ending": {"2024FY": 2000.0},
            "equity.parent": {"2024FY": 1500.0},
            "total_debt.ending": {"2024FY": 100.0},
            "eps.basic": {"2024FY": 9000.0},
        }

    def test_forecast_artifact_contains_dividend_schedule(self):
        ft = self._full_ft()
        result = run_forecast("TEST", ft)
        assert result.dividend_schedule is not None
        assert result.dividend_schedule.method == "historical_median_payout"
        assert result.dividend_schedule.historical_payout_ratio == pytest.approx(0.50, abs=0.01)

    def test_equity_reduced_by_dividends_in_forecast(self):
        """Equity should grow by retained earnings, not full net income."""
        ft_with_div = self._full_ft()
        ft_no_div = {k: v for k, v in ft_with_div.items() if k != "dividends_paid.total"}

        result_with = run_forecast("TEST", ft_with_div)
        result_without = run_forecast("TEST", ft_no_div)

        # With dividends, equity should be lower (50% payout reduces retained earnings)
        eq_with = result_with.forecast_years[-1].equity or 0
        eq_without = result_without.forecast_years[-1].equity or 0
        assert eq_with < eq_without

    def test_dividend_payout_override_applied(self):
        ft = self._full_ft()
        assumptions = ForecastAssumptions(dividend_payout_ratio_override=0.80)
        result = run_forecast("TEST", ft, assumptions=assumptions)
        assert result.dividend_schedule is not None
        assert result.dividend_schedule.historical_payout_ratio == pytest.approx(0.80)
