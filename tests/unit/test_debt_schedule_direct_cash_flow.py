"""With proceeds/repayment facts present, the debt schedule is high-confidence."""
from __future__ import annotations

from backend.facts.normalizer import FactEntry
from backend.analytics.debt_schedule import build_historical_debt_schedule


def _entry(value: float) -> FactEntry:
    return FactEntry(value=value, source_id="vnstock_cfs", source_tier=3, confidence=0.9)


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
