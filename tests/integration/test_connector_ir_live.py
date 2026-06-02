"""Live integration tests for company IR connectors.

Marked with @pytest.mark.integration — skipped in offline/CI mode.
Run manually:
    pytest tests/integration/test_connector_ir_live.py -m integration -v --timeout=30

These tests hit real Vietnamese company websites and CafeF APIs.
They may be slow (5-30 seconds) or return 0 candidates if the site structure
has changed. 0 candidates is a documented finding, not a test failure.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("ticker", ["DHG", "IMP", "DMC", "TRA", "DBD"])
def test_company_ir_connector_returns_candidates(ticker):
    """IR connector must return at least 0 candidates without crashing."""
    from backend.documents.company_registry import get_company
    from backend.documents.connectors.company_ir_connector import CompanyIRConnector

    record = get_company(ticker)
    connector = CompanyIRConnector()
    candidates = connector.discover(record, from_year=2022, to_year=2025)
    assert isinstance(candidates, list), f"Expected list, got {type(candidates)}"
    print(f"\n{ticker}: {len(candidates)} IR candidates found")
    for c in candidates[:3]:
        print(f"  {c.document_type} FY{c.fiscal_year} — {c.source_url[:80]}")


@pytest.mark.parametrize("ticker", ["DHG", "IMP"])
def test_cafef_connector_returns_candidates(ticker):
    """CafeF structured data connector must return rows without crashing."""
    from backend.documents.connectors.cafef_connector import CafeFinanceConnector

    connector = CafeFinanceConnector()
    # Use 2023 as a stable completed fiscal year
    rows = connector.fetch(ticker=ticker, fiscal_year=2023)
    assert isinstance(rows, list), f"Expected list, got {type(rows)}"
    print(f"\n{ticker} CafeF FY2023: {len(rows)} structured rows")
    for r in rows[:5]:
        print(f"  {r.metric_id} = {r.value} {r.unit}")


@pytest.mark.parametrize("ticker", ["DHG", "IMP", "DMC"])
def test_company_ir_connector_ir_urls_present(ticker):
    """Company registry must have at least one IR URL for each MVP ticker."""
    from backend.documents.company_registry import get_company

    record = get_company(ticker)
    assert len(record.ir_urls) >= 1, (
        f"{ticker}: company registry has no IR URLs — cannot discover from company site"
    )
    print(f"\n{ticker} IR URLs: {record.ir_urls}")


@pytest.mark.parametrize("ticker", ["DHG", "IMP", "DMC", "TRA", "DBD"])
def test_company_ir_connector_does_not_crash_on_unreachable_url(ticker, monkeypatch):
    """IR connector must return empty list (not crash) if all IR pages are unreachable."""
    from backend.documents.company_registry import get_company
    from backend.documents.connectors.company_ir_connector import CompanyIRConnector

    def always_fail(url: str) -> str:
        raise ConnectionError(f"Simulated network failure for {url}")

    record = get_company(ticker)
    connector = CompanyIRConnector()
    candidates = connector.discover(record, from_year=2022, to_year=2025,
                                    http_get=always_fail)
    assert candidates == [], (
        f"{ticker}: expected empty list on network failure, got {candidates}"
    )
