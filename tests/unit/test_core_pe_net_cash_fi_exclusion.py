"""Task 3.5: financial_income_already_excluded parameter in compute_core_pe_net_cash.

When False (default): core_eps = eps_forward - ati_per_share  (strips financial income).
When True: core_eps = eps_forward  (no subtraction; avoids double-strip when forecast NI
already excludes financial income).
"""
from __future__ import annotations

import pytest

from backend.analytics.core_pe_net_cash import compute_core_pe_net_cash
from backend.analytics.forecasting import (
    ForecastArtifact,
    ForecastAssumptions,
    ForecastYear,
)
from backend.facts.normalizer import FactEntry


# ── shared fixtures ───────────────────────────────────────────────────────────

_EPS_FORWARD = 10_000.0   # VND/share — FY+1 EPS from forecast
_SHARES_MN = 100.0        # 100 million shares


def _make_forecast(eps: float = _EPS_FORWARD) -> ForecastArtifact:
    fy = ForecastYear(
        year=2026, label="2026F",
        revenue=1_000.0, cogs=-600.0, gross_profit=400.0, gross_margin=0.40,
        sga=-150.0, ebit=250.0, ebit_margin=0.25,
        depreciation=30.0, ebitda=280.0,
        interest_expense=-5.0, profit_before_tax=245.0,
        tax_expense=-49.0, net_income=196.0, net_margin=0.196,
        capex=-20.0,
        total_assets=2_000.0, equity=1_500.0, total_debt=200.0,
        other_liabilities=300.0,
        eps=eps, bvps=150_000.0,
    )
    return ForecastArtifact(
        ticker="TEST",
        historical_periods=["2025FY"],
        forecast_periods=["2026F"],
        assumptions=ForecastAssumptions(),
        revenue_cagr=0.10,
        drivers={},
        forecast_years=[fy],
    )


def _make_fact_table(
    *,
    cash: float = 500.0,
    sti: float = 200.0,
    total_debt: float = 100.0,
    shares: float = _SHARES_MN * 1_000_000,  # stored as raw share count
    vas_ebit: float = 300.0,
    gross_profit: float = 400.0,
    selling_expense: float = -80.0,
    admin_expense: float = -70.0,
) -> dict:
    """Build a minimal fact table using plain dicts (FactEntry not required for _get)."""

    def _fe(v: float) -> FactEntry:
        return FactEntry(value=v, source_id="test", source_title="test", confidence=1.0)

    return {
        "cash_and_equivalents.ending": {"2025FY": _fe(cash)},
        "short_term_investments.ending": {"2025FY": _fe(sti)},
        "total_debt.ending": {"2025FY": _fe(total_debt)},
        "shares_outstanding.ending": {"2025FY": _fe(shares)},
        "ebit.total": {"2025FY": _fe(vas_ebit)},
        "gross_profit.total": {"2025FY": _fe(gross_profit)},
        "selling_expense.total": {"2025FY": _fe(selling_expense)},
        "admin_expense.total": {"2025FY": _fe(admin_expense)},
    }


# ── tests ─────────────────────────────────────────────────────────────────────


class TestCoreEpsWithoutExclusion:
    """Default behaviour: ATI is subtracted from EPS (financial_income_already_excluded=False)."""

    def test_core_eps_subtracts_ati(self):
        # pure_ebit = 400 + (-80) + (-70) = 250; net_fi = 300 - 250 = 50 bn
        # ati_per_share = 50 * (1 - 0.20) * 1000 / 100 = 400 VND/share
        # core_eps = 10_000 - 400 = 9_600
        result = compute_core_pe_net_cash(
            ticker="TEST",
            fact_table=_make_fact_table(),
            forecast=_make_forecast(),
            target_core_pe=19.0,
            financial_income_already_excluded=False,
        )
        assert result.core_eps_vnd is not None
        assert result.core_eps_vnd == pytest.approx(9_600.0, abs=1.0)

    def test_default_parameter_matches_explicit_false(self):
        """Omitting the parameter must behave identically to False."""
        result_default = compute_core_pe_net_cash(
            ticker="TEST",
            fact_table=_make_fact_table(),
            forecast=_make_forecast(),
            target_core_pe=19.0,
        )
        result_explicit = compute_core_pe_net_cash(
            ticker="TEST",
            fact_table=_make_fact_table(),
            forecast=_make_forecast(),
            target_core_pe=19.0,
            financial_income_already_excluded=False,
        )
        assert result_default.core_eps_vnd == result_explicit.core_eps_vnd


class TestCoreEpsWithExclusion:
    """When financial_income_already_excluded=True, ATI is NOT subtracted — core_eps = eps_forward."""

    def test_core_eps_equals_eps_forward(self):
        result = compute_core_pe_net_cash(
            ticker="TEST",
            fact_table=_make_fact_table(),
            forecast=_make_forecast(eps=_EPS_FORWARD),
            target_core_pe=19.0,
            financial_income_already_excluded=True,
        )
        assert result.core_eps_vnd is not None
        assert result.core_eps_vnd == pytest.approx(_EPS_FORWARD, abs=1.0)

    def test_core_eps_excluded_differs_from_default(self):
        """When there is financial income, the two modes must produce different core_eps."""
        result_default = compute_core_pe_net_cash(
            ticker="TEST",
            fact_table=_make_fact_table(),
            forecast=_make_forecast(),
            target_core_pe=19.0,
            financial_income_already_excluded=False,
        )
        result_excluded = compute_core_pe_net_cash(
            ticker="TEST",
            fact_table=_make_fact_table(),
            forecast=_make_forecast(),
            target_core_pe=19.0,
            financial_income_already_excluded=True,
        )
        # With exclusion, core_eps == eps_forward; without, it is lower
        assert result_excluded.core_eps_vnd > result_default.core_eps_vnd

    def test_target_price_uses_full_eps_when_excluded(self):
        """target_price = core_eps * core_pe + net_cash/share."""
        result = compute_core_pe_net_cash(
            ticker="TEST",
            fact_table=_make_fact_table(cash=500.0, sti=200.0, total_debt=100.0),
            forecast=_make_forecast(eps=_EPS_FORWARD),
            target_core_pe=10.0,
            financial_income_already_excluded=True,
        )
        # net_cash = 500 + 200 - 100 = 600 bn; per share = 600_000 / 100 = 6_000 VND
        # target = 10_000 * 10 + 6_000 = 106_000
        assert result.target_price_vnd is not None
        assert result.target_price_vnd == pytest.approx(106_000.0, abs=1.0)

    def test_no_ati_subtraction_when_excluded_and_no_fi_data(self):
        """Even with no financial income data in fact table, exclusion keeps core_eps = eps_forward."""
        ft = _make_fact_table()
        # Remove ebit.total so net_fi cannot be derived
        ft.pop("ebit.total", None)
        result = compute_core_pe_net_cash(
            ticker="TEST",
            fact_table=ft,
            forecast=_make_forecast(),
            target_core_pe=19.0,
            financial_income_already_excluded=True,
        )
        assert result.core_eps_vnd == pytest.approx(_EPS_FORWARD, abs=1.0)
