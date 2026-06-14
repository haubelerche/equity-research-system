from __future__ import annotations

from backend.facts.normalizer import FactEntry
from backend.valuation.data_availability import (
    build_data_availability_matrix,
    build_data_gap_report,
)


def _entry(v: float) -> FactEntry:
    return FactEntry(value=v, source_id="s", source_uri="u", confidence=0.9)


def test_gap_report_lists_missing_fcfe_financing_with_fix():
    table = {
        "operating_cash_flow.total": {"2024FY": _entry(500.0)},
        "capex.total": {"2024FY": _entry(-80.0)},
        "shares_outstanding.ending": {"2024FY": _entry(130.7)},
    }
    matrix = build_data_availability_matrix(
        ticker="DHG",
        fact_table=table,
        latest_period="2024FY",
        available_assumptions={"cost_of_equity", "terminal_growth", "forecast_years"},
        available_market_data={"market_price"},
    )
    report = build_data_gap_report(matrix)
    gaps = {(g["method"], g["field"]): g for g in report["gaps"]}
    key = ("fcfe_dcf", "proceeds_from_borrowings.total")
    assert key in gaps
    assert gaps[key]["classification"] == "ingestion_or_source_absence"
    assert "vnstock" in gaps[key]["recommended_fix"].lower() or "cfs" in gaps[key]["recommended_fix"].lower()


def test_gap_report_empty_when_all_ready():
    table = {
        "operating_cash_flow.total": {"2024FY": _entry(500.0)},
        "capex.total": {"2024FY": _entry(-80.0)},
        "proceeds_from_borrowings.total": {"2024FY": _entry(100.0)},
        "repayment_of_borrowings.total": {"2024FY": _entry(60.0)},
        "shares_outstanding.ending": {"2024FY": _entry(130.7)},
    }
    matrix = build_data_availability_matrix(
        ticker="DHG",
        fact_table=table,
        latest_period="2024FY",
        available_assumptions={"cost_of_equity", "terminal_growth", "forecast_years"},
        available_market_data={"market_price"},
    )
    # Only inspect fcfe_dcf to keep the assertion focused.
    report = build_data_gap_report({"fcfe_dcf": matrix["fcfe_dcf"]})
    assert report["gaps"] == []
    assert report["ready_methods"] == ["fcfe_dcf"]
