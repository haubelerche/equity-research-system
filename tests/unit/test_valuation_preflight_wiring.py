from __future__ import annotations

from backend.facts.normalizer import FactEntry
from backend.valuation.data_availability import run_valuation_preflight


def _entry(v: float) -> FactEntry:
    return FactEntry(value=v, source_id="s", source_uri="u", confidence=0.9)


def test_preflight_returns_matrix_and_gap_report():
    table = {
        "operating_cash_flow.total": {"2024FY": _entry(500.0)},
        "capex.total": {"2024FY": _entry(-80.0)},
        "shares_outstanding.ending": {"2024FY": _entry(130.7)},
    }
    result = run_valuation_preflight(
        ticker="DHG",
        fact_table=table,
        fy_periods=["2023FY", "2024FY"],
        current_price_vnd=92000.0,
        peer_dataset_available=False,
    )
    assert result["ticker"] == "DHG"
    assert result["valuation_date"]  # ISO string present
    assert "data_completeness" in result
    assert "data_gap_report" in result
    # FCFE blocked on missing financing lines; surfaced in the gap report.
    assert result["data_completeness"]["fcfe_dcf"]["status"] == "blocked"
    fcfe_missing = result["data_completeness"]["fcfe_dcf"]["missing_fields"]
    assert "proceeds_from_borrowings.total" in fcfe_missing


def test_preflight_market_price_absent_blocks_market_data():
    table = {"eps.basic": {"2024FY": _entry(5000.0)}, "shares_outstanding.ending": {"2024FY": _entry(130.7)}}
    result = run_valuation_preflight(
        ticker="DHG",
        fact_table=table,
        fy_periods=["2024FY"],
        current_price_vnd=None,
        peer_dataset_available=False,
    )
    assert "market_price" in result["data_completeness"]["pe"]["missing_fields"]
