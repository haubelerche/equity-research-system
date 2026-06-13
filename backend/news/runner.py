"""Ticker news collection orchestration (additive — does not touch the linear graph).

Pipeline: discover candidate URLs from whitelisted feeds → filter to the ticker →
fetch + extract article text → extract factual evidence via the LLM → persist to the
isolated ``news`` schema. Every I/O boundary is injected so the pipeline is testable
offline; ``run_ticker_news_collection`` wires the production defaults and a DB
connection.

The whitelist is enforced at every stage (discovery, collection, evidence build), so a
non-approved domain can never be fetched, stored, or cited.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from backend.news.collector import collect_articles, default_html_fetch, rendered_html_fetch
from backend.news.discovery import discover_candidates
from backend.news.discovery_html import discover_from_listings
from backend.news.evidence_builder import build_evidence, default_llm_extract
from backend.news.extractor import extract_main_content
from backend.news.relevance import build_ticker_keywords, filter_relevant
from backend.news.store import (
    create_research_run,
    evidenced_source_urls,
    get_cron_source_urls,
    link_run_article,
    mark_run_status,
    save_evidence,
    save_raw_article,
    touch_ticker_sources,
    upsert_ticker_source,
)
from backend.news.types import (
    ALLOWED_DOMAINS,
    CITATION_ALLOWED_DOMAINS,
    EvidenceItem,
    RawArticle,
    ResearchPlan,
    source_name_for_domain,
)
from backend.news.whitelist import is_citation_allowed_url, url_domain

# Whitelisted feeds discovered per run. Kept small and explicit; failing feeds are
# skipped by discover_candidates, so an occasional dead URL never aborts a run.
DEFAULT_FEEDS: tuple[tuple[str, str], ...] = (
    ("https://cafef.vn/thi-truong-chung-khoan.rss", "rss"),
    ("https://cafef.vn/doanh-nghiep.rss", "rss"),
    ("https://vnexpress.net/rss/kinh-doanh.rss", "rss"),
    ("https://vneconomy.vn/chung-khoan.rss", "rss"),
    ("https://vietstock.vn/144/chung-khoan/co-phieu.rss", "rss"),
    ("https://vietstock.vn/145/doanh-nghiep.rss", "rss"),
)

# Ticker-scoped news channels (preferred). Discovery is per-company, not broad market
# listings: the CafeF company event index serves DHG-specific article anchors as static
# HTML (parsed by discovery_html, stdlib only). The VietStock ticker page is JS-rendered
# (0 static anchors today — kept for when a rendered fetcher is added). Broad VnExpress/
# VnEconomy crawling is intentionally NOT a default cron source — only contextual fallback.
_TICKER_LISTING_TEMPLATES: tuple[str, ...] = (
    "https://cafef.vn/du-lieu/tin-doanh-nghiep/{ticker_lower}/Event.chn",
    "https://cafef.vn/du-lieu/{exchange_slug}/{ticker_lower}-tin-tuc.chn",
    "https://finance.vietstock.vn/{ticker_upper}/tin-tuc-su-kien.htm",
)

# Broad market listings — fallback only (NOT cron'd by default). Used to add macro/industry
# context, never as the primary ticker feed.
FALLBACK_LISTINGS: tuple[str, ...] = (
    "https://cafef.vn/thi-truong-chung-khoan.chn",
    "https://vnexpress.net/kinh-doanh",
)


# MVP pharma coverage set — the first tickers cron'd for ticker-scoped news.
MVP_TICKERS: tuple[str, ...] = ("DHG", "IMP", "DMC", "TRA", "DBD")


def ticker_listing_urls(ticker: str, exchange_slug: str = "hose") -> tuple[str, ...]:
    """Build the ticker-scoped news listing URLs for one company (CafeF + VietStock)."""
    return tuple(
        template.format(
            ticker_lower=ticker.lower(),
            ticker_upper=ticker.upper(),
            exchange_slug=exchange_slug,
        )
        for template in _TICKER_LISTING_TEMPLATES
    )


# Registry metadata per template, aligned 1:1 with _TICKER_LISTING_TEMPLATES order.
# CafeF event index is the proven static source → highest priority.
_TICKER_SOURCE_META: tuple[dict[str, object], ...] = (
    {"source_name": "CafeF", "source_domain": "cafef.vn", "source_type": "media", "priority": 95},
    {"source_name": "CafeF", "source_domain": "cafef.vn", "source_type": "media", "priority": 94},
    {"source_name": "Vietstock", "source_domain": "vietstock.vn", "source_type": "media", "priority": 90},
)


def build_ticker_sources(ticker: str, exchange_slug: str = "hose") -> list[dict[str, object]]:
    """Registry rows for a ticker's news channels (URLs == ticker_listing_urls)."""
    urls = ticker_listing_urls(ticker, exchange_slug)
    return [
        {**meta, "source_url": url, "is_cron_enabled": True}
        for url, meta in zip(urls, _TICKER_SOURCE_META)
    ]


def default_keywords(ticker: str, company_name: str | None) -> tuple[str, ...]:
    """Discovery/relevance keywords for a ticker (ticker + full + short company name)."""
    return build_ticker_keywords(ticker, company_name)


def gather_ticker_evidence(
    *,
    keywords: Sequence[str],
    feeds: Sequence[tuple[str, str]],
    fetch_xml: Callable[[str], str],
    fetch_html: Callable[[str], str],
    llm_extract: Callable[[str], object],
    ticker: str,
    company_name: str | None,
    topic: str,
    listings: Sequence[str] = (),
    rendered_fetch: Callable[[str], str] | None = None,
    skip_urls: set[str] | None = None,
    max_articles: int = 15,
) -> tuple[list[RawArticle], dict[str, list[EvidenceItem]]]:
    """Run the offline-testable core pipeline and return collected articles + evidence.

    Discovery combines RSS feeds and plain-HTML listing pages (JS-rendered listings use
    ``rendered_fetch``). Candidates in ``skip_urls`` (already-processed articles) are dropped
    before any fetch/LLM call, so repeated runs are idempotent and cheap. No database access:
    callers persist the result separately.
    """
    skip = skip_urls or set()
    candidates = list(discover_candidates(feeds, fetch_xml=fetch_xml))
    if listings:
        seen = {c.source_url for c in candidates}
        for candidate in discover_from_listings(
            listings, fetch_html=fetch_html, rendered_fetch=rendered_fetch
        ):
            if candidate.source_url not in seen:
                seen.add(candidate.source_url)
                candidates.append(candidate)
    relevant = [c for c in filter_relevant(candidates, keywords) if c.source_url not in skip]
    articles = collect_articles(relevant, fetch_html=fetch_html, max_articles=max_articles)

    evidence_by_url: dict[str, list[EvidenceItem]] = {}
    for article in articles:
        items = build_evidence(
            article,
            llm_extract=llm_extract,
            topic=topic,
            ticker=ticker,
            company_name=company_name,
        )
        evidence_by_url[article.source_url] = items
    return articles, evidence_by_url


def ingest_manual_urls(
    *,
    urls: Sequence[str],
    ticker: str,
    company_name: str | None,
    topic: str,
    fetch_html: Callable[[str], str],
    llm_extract: Callable[[str], object],
    max_articles: int = 20,
) -> tuple[list[RawArticle], dict[str, list[EvidenceItem]]]:
    """Fetch + extract + build evidence for human-vetted article URLs (offline-testable).

    Uses the wider citation allowlist: a URL outside it is skipped. The article is still
    untrusted input — it is only ever stored as data and re-validated downstream.
    """
    articles: list[RawArticle] = []
    seen: set[str] = set()
    for url in urls:
        clean = (url or "").strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        if len(articles) >= max_articles:
            break
        if not is_citation_allowed_url(clean):
            continue
        try:
            html = fetch_html(clean)
        except Exception:  # noqa: BLE001 — a failed fetch is skipped, not fatal
            continue
        if not html:
            continue
        extracted = extract_main_content(html)
        if not extracted.text:
            continue
        domain = url_domain(clean) or ""
        articles.append(
            RawArticle(
                source_name=source_name_for_domain(domain),
                source_domain=domain,
                source_url=clean,
                title=extracted.title,
                raw_text=extracted.text,
                published_at=extracted.published_at,
                accessed_at=datetime.now(UTC).isoformat(),
                discovery_method="manual_url",
            )
        )

    evidence_by_url: dict[str, list[EvidenceItem]] = {
        article.source_url: build_evidence(
            article,
            llm_extract=llm_extract,
            topic=topic,
            ticker=ticker,
            company_name=company_name,
            allowed_domains=CITATION_ALLOWED_DOMAINS,
        )
        for article in articles
    }
    return articles, evidence_by_url


def run_manual_url_ingest(
    conn,
    ticker: str,
    company_name: str | None,
    urls: Sequence[str],
    *,
    fetch_html: Callable[[str], str] = default_html_fetch,
    llm_extract: Callable[[str], object] = default_llm_extract,
    max_articles: int = 20,
) -> dict[str, object]:
    """Full production manual-ingest run for human-vetted URLs against a live DB."""
    ticker = ticker.upper()
    topic = f"Tin tức {ticker}" + (f" — {company_name}" if company_name else "")
    plan = ResearchPlan(
        topic=topic,
        keywords=default_keywords(ticker, company_name),
        allowed_domains=tuple(sorted(CITATION_ALLOWED_DOMAINS)),
        ticker=ticker,
        company_name=company_name,
    )
    research_run_id = f"news_manual_{ticker}_{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}"

    articles, evidence_by_url = ingest_manual_urls(
        urls=urls,
        ticker=ticker,
        company_name=company_name,
        topic=topic,
        fetch_html=fetch_html,
        llm_extract=llm_extract,
        max_articles=max_articles,
    )
    counts = persist_ticker_evidence(
        conn,
        plan=plan,
        research_run_id=research_run_id,
        articles=articles,
        evidence_by_url=evidence_by_url,
    )
    conn.commit()
    return {"research_run_id": research_run_id, **counts}


def persist_ticker_evidence(
    conn,
    *,
    plan: ResearchPlan,
    research_run_id: str,
    articles: Sequence[RawArticle],
    evidence_by_url: dict[str, list[EvidenceItem]],
) -> dict[str, int]:
    """Persist a completed pipeline result into the news schema. Returns counts."""
    create_research_run(conn, plan, research_run_id)
    article_count = 0
    evidence_count = 0
    for article in articles:
        article_id = save_raw_article(conn, article)
        link_run_article(conn, research_run_id, article_id, selected=True)
        items = evidence_by_url.get(article.source_url, [])
        if items:
            save_evidence(conn, article_id, items)
            evidence_count += len(items)
        article_count += 1
    mark_run_status(conn, research_run_id, "completed", finished=True)
    return {"articles": article_count, "evidence": evidence_count}


def run_ticker_news_collection(
    conn,
    ticker: str,
    company_name: str | None,
    *,
    exchange_slug: str = "hose",
    feeds: Sequence[tuple[str, str]] = (),
    listings: Sequence[str] | None = None,
    keywords: Sequence[str] | None = None,
    fetch_xml: Callable[[str], str] = default_html_fetch,
    fetch_html: Callable[[str], str] = default_html_fetch,
    rendered_fetch: Callable[[str], str] | None = rendered_html_fetch,
    llm_extract: Callable[[str], object] = default_llm_extract,
    max_articles: int = 15,
) -> dict[str, object]:
    """Full production run for one ticker against a live DB connection.

    Defaults to ticker-scoped CafeF/VietStock discovery (no broad RSS cron); VietStock
    listings are rendered via headless Chrome. Pass ``feeds``/``listings`` to add fallbacks.
    """
    ticker = ticker.upper()
    if listings is None:
        # Prefer the per-ticker source registry; seed it from templates on first run.
        registry_urls = get_cron_source_urls(conn, ticker)
        if not registry_urls:
            for source in build_ticker_sources(ticker, exchange_slug):
                upsert_ticker_source(
                    conn,
                    ticker,
                    source_name=str(source["source_name"]),
                    source_domain=str(source["source_domain"]),
                    source_type=str(source["source_type"]),
                    source_url=str(source["source_url"]),
                    priority=int(source["priority"]),
                    is_cron_enabled=bool(source["is_cron_enabled"]),
                )
            registry_urls = get_cron_source_urls(conn, ticker)
        listings = registry_urls
    topic = f"Tin tức {ticker}" + (f" — {company_name}" if company_name else "")
    keywords = tuple(keywords) if keywords else default_keywords(ticker, company_name)
    plan = ResearchPlan(
        topic=topic,
        keywords=tuple(keywords),
        allowed_domains=tuple(sorted(ALLOWED_DOMAINS)),
        ticker=ticker,
        company_name=company_name,
    )
    research_run_id = f"news_{ticker}_{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}"

    # Skip articles already extracted for this ticker → idempotent, no redundant LLM calls.
    skip_urls = evidenced_source_urls(conn, ticker)

    articles, evidence_by_url = gather_ticker_evidence(
        keywords=keywords,
        feeds=feeds,
        fetch_xml=fetch_xml,
        fetch_html=fetch_html,
        llm_extract=llm_extract,
        ticker=ticker,
        company_name=company_name,
        topic=topic,
        listings=listings,
        rendered_fetch=rendered_fetch,
        skip_urls=skip_urls,
        max_articles=max_articles,
    )
    counts = persist_ticker_evidence(
        conn,
        plan=plan,
        research_run_id=research_run_id,
        articles=articles,
        evidence_by_url=evidence_by_url,
    )
    # The run completed without error — that is source-health success. "No new articles"
    # (idempotent skip) is not a failure, so it must not inflate failure_count.
    touch_ticker_sources(conn, ticker, success=True)
    conn.commit()
    return {
        "research_run_id": research_run_id,
        "candidates_relevant": len(articles),
        **counts,
    }


def collect_for_tickers(
    conn,
    tickers: Sequence[str],
    *,
    company_lookup: Callable[[str], tuple[str, str]],
    collect: Callable[..., dict] = run_ticker_news_collection,
) -> list[dict]:
    """Run ticker-scoped collection for each ticker (the cron entrypoint core).

    Idempotent per ticker (see run_ticker_news_collection). One ticker failing is
    captured and never aborts the batch — cron must keep going for the rest.
    """
    results: list[dict] = []
    for raw in tickers:
        ticker = raw.upper()
        company_name, exchange = company_lookup(ticker)
        try:
            result = collect(conn, ticker, company_name, exchange_slug=exchange.lower())
            results.append({"ticker": ticker, **result})
        except Exception as exc:  # noqa: BLE001 — keep collecting the remaining tickers
            results.append({"ticker": ticker, "error": str(exc)})
    return results
