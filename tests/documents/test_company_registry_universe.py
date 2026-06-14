from __future__ import annotations

from backend.documents.company_registry import all_tickers, get_company, has_company


def test_company_registry_includes_non_mvp_universe_ticker() -> None:
    assert has_company("MKP") is True
    company = get_company("MKP")
    assert company.ticker == "MKP"
    assert company.exchange == "HOSE"
    assert company.issuer_code == "MKP"


def test_company_registry_covers_configured_universe_size() -> None:
    assert len(all_tickers()) >= 53
