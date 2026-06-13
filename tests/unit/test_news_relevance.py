"""Relevance filter: keep only discovered candidates that mention the ticker/company.

Generic business/markets feeds carry many articles; only those naming the company
(by ticker 'DHG' or name 'Dược Hậu Giang', accent-insensitive) are relevant.
"""
from __future__ import annotations

from backend.news.relevance import filter_relevant, is_relevant
from backend.news.types import ArticleCandidate

_KEYWORDS = ("DHG", "Dược Hậu Giang")


def _cand(title: str, url: str = "https://cafef.vn/a.chn", summary: str | None = None) -> ArticleCandidate:
    return ArticleCandidate(
        source_url=url,
        source_domain="cafef.vn",
        source_name="CafeF",
        title=title,
        summary=summary,
    )


def test_matches_ticker_in_title() -> None:
    assert is_relevant(_cand("DHG báo lãi quý 1 tăng mạnh"), _KEYWORDS)


def test_matches_company_name_accent_insensitive() -> None:
    # Article title without diacritics must still match "Dược Hậu Giang".
    assert is_relevant(_cand("Duoc Hau Giang mo rong nha may"), _KEYWORDS)


def test_unrelated_article_is_dropped() -> None:
    assert not is_relevant(_cand("VN-Index tăng điểm phiên cuối tuần"), _KEYWORDS)


def test_filter_keeps_only_relevant() -> None:
    cands = [
        _cand("DHG chốt cổ tức 2025", url="https://cafef.vn/dhg-1.chn"),
        _cand("Thị trường chứng khoán hôm nay", url="https://cafef.vn/x.chn"),
        _cand("Dược Hậu Giang lãi kỷ lục", url="https://vnexpress.net/y.html"),
    ]
    kept = filter_relevant(cands, _KEYWORDS)
    assert [c.source_url for c in kept] == [
        "https://cafef.vn/dhg-1.chn",
        "https://vnexpress.net/y.html",
    ]
