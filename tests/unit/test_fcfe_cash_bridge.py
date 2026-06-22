"""FCFE equity must add non-operating cash + STI, symmetric to FCFF's EV − net_debt.

FCFF reaches equity via EV − net_debt (which credits cash + short-term investments
against debt). FCFE's operating flows already service debt, so a consistent equity
value must add back the same non-operating liquid assets. Without this, FCFE
systematically understates equity for cash-rich firms and diverges from FCFF even
when WACC == Re.
"""
from __future__ import annotations

import pytest

from backend.analytics.fcfe import compute_fcfe, CostOfEquityAssumptions
from backend.analytics.forecasting import run_forecast


def _ft(cash: float, sti: float = 0.0) -> dict:
    # Zero debt -> zero_debt_policy -> FCFE publishable, so we can read equity_value.
    return {
        "revenue.net": {"2023FY": 1500.0, "2024FY": 1700.0, "2025FY": 1865.0},
        "gross_profit.total": {"2023FY": 680.0, "2024FY": 780.0, "2025FY": 884.0},
        "sga.total": {"2023FY": -350.0, "2024FY": -380.0, "2025FY": -418.0},
        "depreciation.total": {"2023FY": 40.0, "2024FY": 44.0, "2025FY": 48.0},
        "capex.total": {"2023FY": -80.0, "2024FY": -90.0, "2025FY": -100.0},
        "total_debt.ending": {"2023FY": 0.0, "2024FY": 0.0, "2025FY": 0.0},
        "cash_and_equivalents.ending": {"2025FY": cash},
        "short_term_investments.ending": {"2025FY": sti},
        "equity.parent": {"2025FY": 1500.0},
        "net_income.parent": {"2023FY": 240.0, "2024FY": 265.0, "2025FY": 292.0},
        "profit_before_tax.total": {"2023FY": 290.0, "2024FY": 320.0, "2025FY": 346.0},
        "tax_expense.total": {"2023FY": -50.0, "2024FY": -55.0, "2025FY": -54.0},
    }


def _equity(cash: float, sti: float = 0.0) -> float:
    ft = _ft(cash, sti)
    forecast = run_forecast("TST", ft, shares_mn=94.45)
    result = compute_fcfe(
        ticker="TST", forecast=forecast, fact_table=ft, shares_mn=94.45,
        cost_of_equity_assumptions=CostOfEquityAssumptions(re_override=0.14),
    )
    return result.equity_value


def test_fcfe_equity_adds_non_operating_cash_and_sti():
    base = _equity(0.0, 0.0)
    with_liquidity = _equity(200.0, 50.0)
    # Equity rises by exactly the added non-operating liquid assets (cash + STI).
    assert with_liquidity - base == pytest.approx(250.0)


def test_fcfe_preserves_forecast_net_income_semantics():
    ft = _ft(cash=100.0, sti=20.0)
    forecast = run_forecast("TST", ft, shares_mn=94.45)
    result = compute_fcfe(
        ticker="TST", forecast=forecast, fact_table=ft, shares_mn=94.45,
        cost_of_equity_assumptions=CostOfEquityAssumptions(re_override=0.14),
    )

    assert result.forecast_years[0].net_income == pytest.approx(
        forecast.forecast_years[0].net_income
    )
