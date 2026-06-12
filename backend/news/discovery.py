"""Discovery worker — find candidate article URLs from whitelisted feeds (plan §4.2).

RSS/Atom and sitemap (incl. Google-News sitemap) are parsed with the stdlib XML parser; no
third-party feed library is required. Fetching is injected (`fetch_xml`) so discovery is
deterministic and testable with no network. Every discovered link is passed through the
whitelist gate — a non-approved link is never returned.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from xml.etree import ElementTree as ET

from backend.news.types import ArticleCandidate, source_name_for_domain
from backend.news.whitelist import is_allowed_url

_ATOM_NS = "{http://www.w3.org/2005/Atom}"
_SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
_NEWS_NS = "{http://www.google.com/schemas/sitemap-news/0.9}"


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _text(element: ET.Element | None) -> str | None:
    if element is None or element.text is None:
        return None
    value = element.text.strip()
    return value or None


def _find_child(parent: ET.Element, localname: str) -> ET.Element | None:
    for child in parent:
        if _localname(child.tag) == localname:
            return child
    return None


def _parse_xml(xml: str) -> ET.Element | None:
    try:
        return ET.fromstring(xml)
    except ET.ParseError:
        return None


def parse_rss(xml: str, *, source_domain: str) -> list[ArticleCandidate]:
    """Parse RSS 2.0 or Atom; return whitelisted candidates for source_domain."""
    root = _parse_xml(xml)
    if root is None:
        return []
    source_name = source_name_for_domain(source_domain)
    candidates: list[ArticleCandidate] = []

    # RSS 2.0: rss/channel/item ; Atom: feed/entry
    items = [el for el in root.iter() if _localname(el.tag) in {"item", "entry"}]
    for item in items:
        link = _extract_link(item)
        if not link or not is_allowed_url(link):
            continue
        title = _text(_find_child(item, "title"))
        published = _text(_find_child(item, "pubdate")) or _text(_find_child(item, "updated"))
        summary = _text(_find_child(item, "description")) or _text(_find_child(item, "summary"))
        candidates.append(
            ArticleCandidate(
                source_url=link,
                source_domain=source_domain,
                source_name=source_name,
                title=title,
                published_at=published,
                summary=summary,
                discovery_method="rss",
            )
        )
    return candidates


def _extract_link(item: ET.Element) -> str | None:
    # RSS: <link>text</link> ; Atom: <link href="..."/>
    link_el = _find_child(item, "link")
    if link_el is not None:
        href = link_el.attrib.get("href")
        if href:
            return href.strip()
        if link_el.text and link_el.text.strip():
            return link_el.text.strip()
    return None


def parse_sitemap(xml: str, *, source_domain: str) -> list[ArticleCandidate]:
    """Parse a sitemap / Google-News sitemap; return whitelisted candidates for source_domain."""
    root = _parse_xml(xml)
    if root is None:
        return []
    source_name = source_name_for_domain(source_domain)
    candidates: list[ArticleCandidate] = []
    for url_el in root.iter():
        if _localname(url_el.tag) != "url":
            continue
        loc = _text(_find_child(url_el, "loc"))
        if not loc or not is_allowed_url(loc):
            continue
        title = None
        published = _text(_find_child(url_el, "lastmod"))
        news_el = _find_child(url_el, "news")
        if news_el is not None:
            title = _text(_find_child(news_el, "title"))
            published = _text(_find_child(news_el, "publication_date")) or published
        candidates.append(
            ArticleCandidate(
                source_url=loc,
                source_domain=source_domain,
                source_name=source_name,
                title=title,
                published_at=published,
                discovery_method="sitemap",
            )
        )
    return candidates


def discover_candidates(
    sources: Iterable[tuple[str, str]],
    *,
    fetch_xml: Callable[[str], str],
) -> list[ArticleCandidate]:
    """Discover candidates from (feed_url, kind) sources; kind is 'rss' or 'sitemap'.

    A failing source (network error, bad domain) is skipped — it must not abort discovery.
    Candidates are deduplicated by source_url, preserving first-seen order.
    """
    from backend.news.whitelist import url_domain

    seen: set[str] = set()
    out: list[ArticleCandidate] = []
    for feed_url, kind in sources:
        domain = url_domain(feed_url)
        if domain is None or not is_allowed_url(feed_url):
            continue
        try:
            xml = fetch_xml(feed_url)
        except Exception:  # noqa: BLE001 — a failing feed must not abort discovery
            continue
        parser = parse_sitemap if kind == "sitemap" else parse_rss
        for candidate in parser(xml, source_domain=domain):
            if candidate.source_url in seen:
                continue
            seen.add(candidate.source_url)
            out.append(candidate)
    return out
