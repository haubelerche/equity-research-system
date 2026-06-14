"""End-to-end-ish regression for the data completeness layer.

Synthetic-complete table → every method ready.
Synthetic table missing the CFS financing lines → FCFE blocked with the exact
two missing fields (mirrors the real DHG/DBD condition before the ingestion fix).
"""
from __future__ import annotations

from backend.facts.normalizer import FactEntry
from backend.valuation.data_availability import run_valuation_preflight


def _e(v: float) -> FactEntry:
    return FactEntry(value=v, source_id="s", source_uri="https://audited", source_tier=0, confidence=0.95)


def _complete_table(period: str = "2024FY") -> dict:
    return {
        "revenue.net": {period: _e(4000.0)},
        "ebit.total": {period: _e(700.0)},
        "tax_expense.total": {period: _e(140.0)},
        "da.total": {period: _e(120.0)},
        "capex.total": {period: _e(-150.0)},
        "change_in_working_capital.total": {period: _e(30.0)},
        "cash_and_equivalents.ending": {period: _e(900.0)},
        "short_term_debt.ending": {period: _e(50.0)},
        "long_term_debt.ending": {period: _e(40.0)},
        "shares_outstanding.ending": {period: _e(130.7)},
        "operating_cash_flow.total": {period: _e(620.0)},
        "proceeds_from_borrowings.total": {period: _e(100.0)},
        "repayment_of_borrowings.total": {period: _e(60.0)},
        "eps.basic": {period: _e(5300.0)},
    }


def test_synthetic_complete_artifact_all_dcf_methods_ready():
    result = run_valuation_preflight(
        ticker="SYN",
        fact_table=_complete_table(),
        fy_periods=["2022FY", "2023FY", "2024FY"],
        current_price_vnd=92000.0,
        peer_dataset_available=True,  # synthetic supplies peers too
    )
    dc = result["data_completeness"]
    assert dc["fcff_dcf"]["status"] == "ready"
    assert dc["fcfe_dcf"]["status"] == "ready"
    assert dc["pe"]["status"] == "ready"
    assert dc["ev_ebitda"]["status"] == "ready"
    assert result["data_gap_report"]["gaps"] == []


def test_missing_cfs_financing_blocks_only_fcfe_financing_fields():
    table = _complete_table()
    del table["proceeds_from_borrowings.total"]
    del table["repayment_of_borrowings.total"]
    result = run_valuation_preflight(
        ticker="DHG",
        fact_table=table,
        fy_periods=["2022FY", "2023FY", "2024FY"],
        current_price_vnd=92000.0,
        peer_dataset_available=True,
    )
    dc = result["data_completeness"]
    # FCFF/PE/EV-EBITDA do not need the gross financing lines → still ready.
    assert dc["fcff_dcf"]["status"] == "ready"
    assert dc["fcfe_dcf"]["status"] == "blocked"
    assert set(dc["fcfe_dcf"]["missing_fields"]) == {
        "proceeds_from_borrowings.total",
        "repayment_of_borrowings.total",
    }
    # The gap report names the fix.
    fcfe_gaps = [g for g in result["data_gap_report"]["gaps"] if g["method"] == "fcfe_dcf"]
    assert len(fcfe_gaps) == 2
    assert all(g["classification"] == "ingestion_or_source_absence" for g in fcfe_gaps)
