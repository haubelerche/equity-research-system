"""Citation relevance keywords: ticker + full + prefix-stripped company name.

Article titles use the short company name ("Dược Hậu Giang"), while the registry stores
the legal form ("Công ty CP Dược Hậu Giang"). Matching must work on the short core too.
"""
from __future__ import annotations

from backend.news.relevance import build_ticker_keywords
from backend.reporting.client_report_view_model import _evidence_to_citations


def test_includes_ticker_full_and_stripped_company_name() -> None:
    kws = build_ticker_keywords("DHG", "Công ty CP Dược Hậu Giang")
    assert "DHG" in kws
    assert "Công ty CP Dược Hậu Giang" in kws
    assert "Dược Hậu Giang" in kws


def test_cafef_short_title_now_matches() -> None:
    kws = build_ticker_keywords("DHG", "Công ty CP Dược Hậu Giang")
    rows = [
        {"source_name": "CafeF", "title": "Dược Hậu Giang thay CEO", "url": "u1",
         "published_at": "", "claim": "..."},
    ]
    cits = _evidence_to_citations(rows, kws)
    assert [c["url"] for c in cits] == ["u1"]
