"""Relevance filter + shared ticker keyword/normalize helpers.

Generic markets/business feeds carry far more than one company. Before any article
is fetched or sent to the LLM, candidates are filtered down to those whose title,
summary or URL mention the ticker or company name. Matching is accent-insensitive
so a headline written without Vietnamese diacritics still matches the proper name.

This module is the single home for Vietnamese text normalization and ticker-keyword
building; both the news pipeline and the report citation loader import from here.
"""
from __future__ import annotations

import unicodedata
from collections.abc import Iterable, Sequence

from backend.news.types import ArticleCandidate

# Vietnamese corporate-form prefixes stripped to get a short company core for matching
# (registry stores "Công ty CP Dược Hậu Giang"; article titles use "Dược Hậu Giang").
_CORP_PREFIXES = (
    "công ty cổ phần",
    "tổng công ty cổ phần",
    "công ty cp",
    "ctcp",
    "tổng công ty",
    "công ty tnhh",
    "công ty",
    "tập đoàn",
    "ngân hàng tmcp",
)


def normalize_vi(text: str | None) -> str:
    """Lowercase + strip Vietnamese diacritics (đ→d) for tolerant substring matching."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return stripped.replace("đ", "d").replace("Đ", "D").casefold()


def build_ticker_keywords(ticker: str, company_name: str | None) -> tuple[str, ...]:
    """Relevance keywords: ticker, full company name, and the prefix-stripped short core."""
    keywords: list[str] = [ticker.upper()]
    name = (company_name or "").strip()
    if name:
        keywords.append(name)
        lowered = name.lower()
        for prefix in _CORP_PREFIXES:
            if lowered.startswith(prefix):
                short = name[len(prefix):].strip()
                if short and short not in keywords:
                    keywords.append(short)
                break
    return tuple(keywords)


def is_relevant(candidate: ArticleCandidate, keywords: Sequence[str]) -> bool:
    """True if any keyword appears in the candidate's title, summary or URL."""
    haystack = normalize_vi(
        " ".join(filter(None, [candidate.title, candidate.summary, candidate.source_url]))
    )
    return any(normalize_vi(keyword) in haystack for keyword in keywords if keyword)


def filter_relevant(
    candidates: Iterable[ArticleCandidate], keywords: Sequence[str]
) -> list[ArticleCandidate]:
    """Keep candidates that mention the ticker/company, preserving order."""
    return [candidate for candidate in candidates if is_relevant(candidate, keywords)]
