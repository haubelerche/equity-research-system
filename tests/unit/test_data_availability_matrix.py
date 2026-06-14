from __future__ import annotations

from backend.facts.normalizer import FactEntry
from backend.valuation.data_availability import build_data_availability_matrix


def _entry(value: float, uri: str = "https://src", conf: float = 0.9) -> FactEntry:
    return FactEntry(value=value, source_id="s", source_uri=uri, source_tier=1, confidence=conf)


def _fcfe_complete_table() -> dict:
    p = "2024FY"
    return {
        "operating_cash_flow.total": {p: _entry(500.0)},
        "capex.total": {p: _entry(-80.0)},
        "proceeds_from_borrowings.total": {p: _entry(100.0)},
        "repayment_of_borrowings.total": {p: _entry(60.0)},
        "shares_outstanding.ending": {p: _entry(130.7)},
    }


def test_fcfe_ready_when_all_facts_present():
    matrix = build_data_availability_matrix(
        ticker="DHG",
        fact_table=_fcfe_complete_table(),
        latest_period="2024FY",
        available_assumptions={"cost_of_equity", "terminal_growth", "forecast_years"},
        available_market_data={"market_price"},
    )
    fcfe = matrix["fcfe_dcf"]
    assert fcfe["status"] == "ready"
    assert fcfe["missing_fields"] == []
    assert fcfe["available_count"] == fcfe["required_count"]


def test_fcfe_blocked_lists_exact_missing_financing_fields():
    table = _fcfe_complete_table()
    del table["proceeds_from_borrowings.total"]
    del table["repayment_of_borrowings.total"]
    matrix = build_data_availability_matrix(
        ticker="DHG",
        fact_table=table,
        latest_period="2024FY",
        available_assumptions={"cost_of_equity", "terminal_growth", "forecast_years"},
        available_market_data={"market_price"},
    )
    fcfe = matrix["fcfe_dcf"]
    assert fcfe["status"] == "blocked"
    assert set(fcfe["missing_fields"]) == {
        "proceeds_from_borrowings.total",
        "repayment_of_borrowings.total",
    }


def test_field_detail_carries_lineage_for_present_facts():
    matrix = build_data_availability_matrix(
        ticker="DHG",
        fact_table=_fcfe_complete_table(),
        latest_period="2024FY",
        available_assumptions={"cost_of_equity", "terminal_growth", "forecast_years"},
        available_market_data={"market_price"},
    )
    detail = {d["canonical_field"]: d for d in matrix["fcfe_dcf"]["field_details"]}
    cfo = detail["operating_cash_flow.total"]
    assert cfo["available"] is True
    assert cfo["latest_period"] == "2024FY"
    assert cfo["source_uri"] == "https://src"
    assert cfo["confidence"] == 0.9
    assert cfo["classification"] == "available"


def test_missing_assumption_and_market_data_block_method():
    matrix = build_data_availability_matrix(
        ticker="DHG",
        fact_table=_fcfe_complete_table(),
        latest_period="2024FY",
        available_assumptions=set(),          # no assumptions supplied
        available_market_data=set(),          # no market price
    )
    fcfe = matrix["fcfe_dcf"]
    assert fcfe["status"] == "blocked"
    assert "cost_of_equity" in fcfe["missing_fields"]
    assert "market_price" in fcfe["missing_fields"]


def test_pe_blocked_on_missing_peer_market_data():
    table = {
        "eps.basic": {"2024FY": _entry(5000.0)},
        "shares_outstanding.ending": {"2024FY": _entry(130.7)},
    }
    matrix = build_data_availability_matrix(
        ticker="DHG",
        fact_table=table,
        latest_period="2024FY",
        available_assumptions=set(),
        available_market_data={"market_price"},  # peer data absent
    )
    pe = matrix["pe"]
    assert pe["status"] == "blocked"
    assert "peer_pe_median" in pe["missing_fields"]
    assert "peer_group" in pe["missing_fields"]
