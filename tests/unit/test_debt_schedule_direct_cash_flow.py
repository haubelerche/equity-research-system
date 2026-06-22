"""With proceeds/repayment facts present, the debt schedule is high-confidence."""
from __future__ import annotations

import pytest

from backend.facts.normalizer import FactEntry
from backend.analytics.debt_schedule import (
    build_debt_schedule,
    build_historical_debt_schedule,
)


def _entry(value: float) -> FactEntry:
    return FactEntry(value=value, source_id="vnstock_cfs", source_tier=3, confidence=0.9)


def _cfs_fact_table() -> dict:
    # Debt is a constant 10% of revenue both historical years (leverage = 0.10),
    # with CFS borrowing facts present so history is direct_cash_flow.
    return {
        "total_debt.ending": {"2023FY": _entry(100.0), "2024FY": _entry(120.0)},
        "revenue.net": {"2023FY": _entry(1000.0), "2024FY": _entry(1200.0)},
        "proceeds_from_borrowings.total": {"2023FY": _entry(30.0), "2024FY": _entry(50.0)},
        "repayment_of_borrowings.total": {"2023FY": _entry(10.0), "2024FY": _entry(30.0)},
        "interest_expense.total": {"2023FY": _entry(6.0), "2024FY": _entry(7.0)},
    }


def test_forecast_direct_cash_flow_projects_leverage_and_publishes_fcfe():
    """A debt-carrying company whose net borrowing is CFS-sourced gets a forecast
    debt path at its historical leverage (debt tracks revenue) -> direct_cash_flow,
    FCFE publishable. Previously such firms fell to stable_debt -> FCFE blocked."""
    sched = build_debt_schedule(
        "TST", _cfs_fact_table(), ["2023FY", "2024FY"],
        forecast_labels=["2025F", "2026F"], forecast_years=[2025, 2026],
        forecast_revenue={"2025F": 1320.0, "2026F": 1452.0},  # +10%/yr
    )
    assert sched.forecast_method == "direct_cash_flow"
    assert sched.is_fcfe_publishable is True
    r25 = next(r for r in sched.forecast_rows if r.label == "2025F")
    # leverage = median(0.10, 0.10) = 0.10; ending = 0.10*1320 = 132; nb = 132-120 = 12
    assert r25.ending_interest_bearing_debt == pytest.approx(132.0)
    assert r25.net_borrowing == pytest.approx(12.0)
    assert all(r.confidence == "high" for r in sched.forecast_rows)


def test_forecast_falls_back_to_stable_debt_without_forecast_revenue():
    """No revenue forecast -> cannot project leverage -> hold flat (FCFE blocked).
    The CFS-corroborated path must not fire without a revenue path to scale against."""
    sched = build_debt_schedule(
        "TST", _cfs_fact_table(), ["2023FY", "2024FY"],
        forecast_labels=["2025F", "2026F"], forecast_years=[2025, 2026],
    )
    assert sched.forecast_method == "stable_debt"
    assert sched.is_fcfe_publishable is False


def test_direct_cash_flow_method_when_financing_facts_present():
    # VND bn (analytics contract). 2024 borrowings = 100 drawn, 60 repaid.
    fact_table = {
        "total_debt.ending": {"2023FY": _entry(50.0), "2024FY": _entry(90.0)},
        "proceeds_from_borrowings.total": {"2024FY": _entry(100.0)},
        "repayment_of_borrowings.total": {"2024FY": _entry(60.0)},
        "interest_expense.total": {"2024FY": _entry(5.0)},
    }
    rows = build_historical_debt_schedule("DHG", fact_table, ["2023FY", "2024FY"])
    row_2024 = next(r for r in rows if r.label == "2024FY")
    assert row_2024.method == "direct_cash_flow"
    assert row_2024.confidence == "high"
    # net_borrowing = proceeds - abs(repayment) = 100 - 60 = 40
    assert row_2024.net_borrowing == 40.0


def test_falls_back_to_balance_sheet_delta_without_financing_facts():
    fact_table = {
        "total_debt.ending": {"2023FY": _entry(50.0), "2024FY": _entry(90.0)},
    }
    rows = build_historical_debt_schedule("DHG", fact_table, ["2023FY", "2024FY"])
    row_2024 = next(r for r in rows if r.label == "2024FY")
    assert row_2024.method == "balance_sheet_delta"
    assert row_2024.confidence == "medium"
