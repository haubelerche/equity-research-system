"""Article collector — fetch public article pages and extract clean text (plan §4.4).

Fetching is injected (`fetch_html`) so the collector is deterministic and network-free in
tests; the default fetcher (`default_html_fetch`) is a thin TLS-verified urllib wrapper used
in production. The collector re-applies the whitelist gate to every candidate (defense in
depth) and caps the number of articles per run. It does not bypass paywalls or login walls —
it only fetches whatever bytes the injected fetcher returns.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, datetime

from backend.news.extractor import extract_main_content
from backend.news.types import ArticleCandidate, RawArticle
from backend.news.whitelist import is_allowed_url

# Plan §4.4 recommended crawl ceiling.
DEFAULT_MAX_ARTICLES = 30

FetchHtml = Callable[[str], str]


def default_html_fetch(url: str, timeout: int = 15) -> str:
    """TLS-verified urllib fetch (production default). Tests inject a stub instead."""
    import urllib.request

    req = urllib.request.Request(url, headers={"User-Agent": "maer-news-collector/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — verified TLS
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def rendered_html_fetch(url: str, timeout: int = 40) -> str:
    """Return a JS-rendered page's DOM via headless Chrome `--dump-dom`.

    For listing pages whose article links are injected by JavaScript (e.g. VietStock).
    Reuses the installed Chromium/Chrome/Edge binary; returns "" if none is available or
    rendering fails — discovery then simply finds no candidates from that source.
    """
    import subprocess

    from backend.reporting.pdf_renderer import _find_chromium_executable

    chrome = _find_chromium_executable()
    if chrome is None:
        return ""
    try:
        result = subprocess.run(  # noqa: S603 — fixed args, URL is whitelisted upstream
            [
                str(chrome),
                "--headless=new",
                "--disable-gpu",
                "--no-sandbox",
                "--virtual-time-budget=15000",
                "--dump-dom",
                url,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except Exception:  # noqa: BLE001 — a render failure yields no candidates, never a crash
        return ""
    return result.stdout or ""


def collect_article(candidate: ArticleCandidate, *, fetch_html: FetchHtml) -> RawArticle | None:
    """Fetch + extract a single candidate. Returns None on whitelist/fetch/empty failure."""
    if not is_allowed_url(candidate.source_url):
        return None
    try:
        html = fetch_html(candidate.source_url)
    except Exception:  # noqa: BLE001 — a failed fetch is skipped, not fatal
        return None
    if not html:
        return None
    extracted = extract_main_content(html)
    if not extracted.text:
        return None
    return RawArticle(
        source_name=candidate.source_name,
        source_domain=candidate.source_domain,
        source_url=candidate.source_url,
        title=candidate.title or extracted.title,
        raw_text=extracted.text,
        published_at=candidate.published_at or extracted.published_at,
        accessed_at=datetime.now(UTC).isoformat(),
        summary=candidate.summary,
        discovery_method=candidate.discovery_method,
    )


def collect_articles(
    candidates: Iterable[ArticleCandidate],
    *,
    fetch_html: FetchHtml,
    max_articles: int = DEFAULT_MAX_ARTICLES,
) -> list[RawArticle]:
    """Collect up to max_articles whitelisted candidates, skipping duplicates and failures."""
    seen: set[str] = set()
    articles: list[RawArticle] = []
    for candidate in candidates:
        if len(articles) >= max_articles:
            break
        if candidate.source_url in seen:
            continue
        seen.add(candidate.source_url)
        article = collect_article(candidate, fetch_html=fetch_html)
        if article is not None:
            articles.append(article)
    return articles
