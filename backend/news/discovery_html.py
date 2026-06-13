"""HTML-listing discovery worker — find article URLs on plain-HTML listing pages (stdlib).

Some whitelisted sites expose section listings as static HTML rather than RSS (e.g. CafeF
``*.chn`` pages, VnExpress section pages). This worker parses anchors with the stdlib
HTMLParser (no bs4/selenium — matching backend/news/extractor.py), keeps only whitelisted,
article-shaped URLs, and returns ArticleCandidates for the same downstream pipeline that
RSS discovery feeds (whitelist → relevance → collect → evidence).
"""
from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from html.parser import HTMLParser

from backend.news.types import ArticleCandidate, source_name_for_domain
from backend.news.whitelist import is_allowed_url, url_domain

# An article URL ends in a long numeric id then .chn/.html/.htm (CafeF/VnExpress/Vietstock).
# Section/nav links (e.g. /thi-truong-chung-khoan.chn) have no such id and are skipped.
_ARTICLE_URL_RE = re.compile(r"\d{6,}\.(?:chn|html|htm)(?:[?#]|$)", re.IGNORECASE)


class _AnchorCollector(HTMLParser):
    """Collect (href, anchor_text) pairs from a listing page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.anchors: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self._href = href.strip()
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            self.anchors.append((self._href, " ".join("".join(self._text).split())))
            self._href = None
            self._text = []


def _resolve(href: str, source_domain: str) -> str:
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("/"):
        return f"https://{source_domain}{href}"
    return href


def parse_listing_anchors(html: str, *, source_domain: str) -> list[ArticleCandidate]:
    """Return whitelisted, article-shaped candidates from one listing page's HTML."""
    collector = _AnchorCollector()
    try:
        collector.feed(html or "")
    except Exception:  # noqa: BLE001 — a malformed page yields no candidates, never a crash
        return []

    seen: set[str] = set()
    candidates: list[ArticleCandidate] = []
    for href, text in collector.anchors:
        if not href:
            continue
        url = _resolve(href, source_domain)
        if not _ARTICLE_URL_RE.search(url) or not is_allowed_url(url):
            continue
        if url in seen:
            continue
        seen.add(url)
        domain = url_domain(url) or source_domain
        candidates.append(
            ArticleCandidate(
                source_url=url,
                source_domain=domain,
                source_name=source_name_for_domain(domain),
                title=text or None,
                discovery_method="html_listing",
            )
        )
    return candidates


# Hosts whose listing pages are JS-rendered → need a rendered (headless-browser) fetch.
_NEEDS_RENDER = ("vietstock.vn",)


def _needs_render(domain: str) -> bool:
    return any(domain == d or domain.endswith("." + d) for d in _NEEDS_RENDER)


def discover_from_listings(
    listing_urls: Iterable[str],
    *,
    fetch_html: Callable[[str], str],
    rendered_fetch: Callable[[str], str] | None = None,
) -> list[ArticleCandidate]:
    """Fetch each whitelisted listing page and aggregate article candidates (deduped).

    JS-rendered listings (e.g. VietStock) use ``rendered_fetch`` when provided; static
    listings (e.g. CafeF .chn) use ``fetch_html``. A failing listing is skipped, never fatal.
    """
    seen: set[str] = set()
    out: list[ArticleCandidate] = []
    for listing_url in listing_urls:
        domain = url_domain(listing_url)
        if domain is None or not is_allowed_url(listing_url):
            continue
        fetcher = fetch_html
        if rendered_fetch is not None and _needs_render(domain):
            fetcher = rendered_fetch
        try:
            html = fetcher(listing_url)
        except Exception:  # noqa: BLE001 — a failing listing must not abort discovery
            continue
        for candidate in parse_listing_anchors(html, source_domain=domain):
            if candidate.source_url in seen:
                continue
            seen.add(candidate.source_url)
            out.append(candidate)
    return out
