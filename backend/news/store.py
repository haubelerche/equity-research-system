"""Data-access layer for the `news` schema (plan §5, §9).

Thin psycopg2 DAL. Every function takes an open connection so callers own the transaction
(matching backend/database/migrate.py). All writes are parameterized — article/evidence text
is untrusted and must never be string-interpolated into SQL. The whitelist is also enforced by
a DB CHECK on news.raw_articles.source_domain, so a non-approved article cannot be inserted.
"""
from __future__ import annotations

import json
from collections.abc import Sequence

from backend.news.types import EvidenceItem, RawArticle, ResearchPlan

_EVIDENCE_SELECT_COLUMNS = (
    "claim, evidence_text, evidence_type, confidence, source_name, source_domain, "
    "source_url, topic, ticker, company_name, published_at, accessed_at"
)


def _row_to_evidence(row: Sequence) -> EvidenceItem:
    """Map a SELECT row (in _EVIDENCE_SELECT_COLUMNS order) to an EvidenceItem."""
    (
        claim,
        evidence_text,
        evidence_type,
        confidence,
        source_name,
        source_domain,
        source_url,
        topic,
        ticker,
        company_name,
        published_at,
        accessed_at,
    ) = row
    return EvidenceItem(
        claim=claim,
        evidence_text=evidence_text,
        evidence_type=evidence_type,
        confidence=confidence or "medium",
        source_name=source_name,
        source_domain=source_domain,
        source_url=source_url,
        topic=topic,
        ticker=ticker,
        company_name=company_name,
        published_at=str(published_at) if published_at is not None else None,
        accessed_at=str(accessed_at) if accessed_at is not None else None,
    )


def create_research_run(
    conn,
    plan: ResearchPlan,
    research_run_id: str,
    *,
    user_id: str | None = None,
    query: str | None = None,
) -> str:
    """Insert a news.research_runs row (status='running'). Returns research_run_id."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO news.research_runs
                (research_run_id, user_id, topic, ticker, company_name, query, keywords, allowed_domains)
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
            ON CONFLICT (research_run_id) DO NOTHING
            """,
            (
                research_run_id,
                user_id,
                plan.topic,
                plan.ticker,
                plan.company_name,
                query,
                json.dumps(list(plan.keywords)),
                json.dumps(list(plan.allowed_domains)),
            ),
        )
    return research_run_id


def save_raw_article(conn, article: RawArticle) -> int:
    """Upsert a news.raw_articles row keyed on source_url. Returns article_id."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO news.raw_articles
                (source_name, source_domain, source_url, title, summary, published_at,
                 accessed_at, raw_text, discovery_method, extraction_method)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_url) DO UPDATE SET
                title = EXCLUDED.title,
                summary = EXCLUDED.summary,
                raw_text = EXCLUDED.raw_text,
                published_at = EXCLUDED.published_at,
                updated_at = NOW()
            RETURNING article_id
            """,
            (
                article.source_name,
                article.source_domain,
                article.source_url,
                article.title,
                article.summary,
                article.published_at,
                article.accessed_at,
                article.raw_text,
                article.discovery_method,
                article.extraction_method,
            ),
        )
        return cur.fetchone()[0]


def link_run_article(
    conn,
    research_run_id: str,
    article_id: int,
    *,
    relevance_score: float | None = None,
    selected: bool = False,
) -> None:
    """Link an article to a research run (news.research_run_articles)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO news.research_run_articles
                (research_run_id, article_id, relevance_score, selected)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (research_run_id, article_id) DO UPDATE SET
                relevance_score = EXCLUDED.relevance_score,
                selected = EXCLUDED.selected
            """,
            (research_run_id, article_id, relevance_score, selected),
        )


def save_evidence(conn, article_id: int, items: list[EvidenceItem]) -> list[int]:
    """Insert evidence rows for one article, idempotently. Returns newly-inserted ids.

    A repeated collection run for the same ticker re-extracts the same claims; the
    unique index on (article_id, md5(claim)) + ON CONFLICT DO NOTHING means an identical
    claim is stored once, so cron re-runs never duplicate evidence.
    """
    ids: list[int] = []
    for item in items:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO news.extracted_evidence
                    (article_id, topic, ticker, company_name, claim, evidence_text, evidence_type,
                     source_name, source_domain, source_url, published_at, accessed_at, confidence)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (article_id, md5(claim)) DO NOTHING
                RETURNING evidence_id
                """,
                (
                    article_id,
                    item.topic,
                    item.ticker,
                    item.company_name,
                    item.claim,
                    item.evidence_text,
                    item.evidence_type,
                    item.source_name,
                    item.source_domain,
                    item.source_url,
                    item.published_at,
                    item.accessed_at,
                    item.confidence,
                ),
            )
            row = cur.fetchone()
            if row is not None:  # None when the row already existed (ON CONFLICT DO NOTHING)
                ids.append(row[0])
    return ids


def upsert_ticker_source(
    conn,
    ticker: str,
    *,
    source_name: str,
    source_domain: str,
    source_type: str,
    source_url: str,
    priority: int,
    is_cron_enabled: bool = True,
) -> None:
    """Insert/update a per-ticker news source (news.ticker_news_sources)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO news.ticker_news_sources
                (ticker, source_name, source_domain, source_type, source_url, priority, is_cron_enabled)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (ticker, source_url) DO UPDATE SET
                source_name = EXCLUDED.source_name,
                source_domain = EXCLUDED.source_domain,
                source_type = EXCLUDED.source_type,
                priority = EXCLUDED.priority,
                is_cron_enabled = EXCLUDED.is_cron_enabled,
                updated_at = NOW()
            """,
            (ticker.upper(), source_name, source_domain, source_type, source_url, priority, is_cron_enabled),
        )


def get_cron_source_urls(conn, ticker: str) -> list[str]:
    """Enabled news-source URLs for a ticker, highest priority first."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT source_url FROM news.ticker_news_sources "
            "WHERE ticker = %s AND is_cron_enabled ORDER BY priority DESC, id",
            (ticker.upper(),),
        )
        return [row[0] for row in cur.fetchall()]


def touch_ticker_sources(conn, ticker: str, *, success: bool) -> None:
    """Record a collection attempt: bump last_checked_at (+ last_success_at / failure_count)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE news.ticker_news_sources SET
                last_checked_at = NOW(),
                last_success_at = CASE WHEN %s THEN NOW() ELSE last_success_at END,
                failure_count = CASE WHEN %s THEN 0 ELSE failure_count + 1 END
            WHERE ticker = %s AND is_cron_enabled
            """,
            (success, success, ticker.upper()),
        )


def evidenced_source_urls(conn, ticker: str) -> set[str]:
    """Source URLs that already have >=1 extracted evidence row for this ticker.

    Used to skip re-fetching/re-extracting already-processed articles on repeated
    (cron) runs — making collection idempotent and avoiding redundant LLM calls.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT source_url FROM news.extracted_evidence WHERE ticker = %s",
            (ticker,),
        )
        return {row[0] for row in cur.fetchall()}


def get_evidence_by_ticker(conn, ticker: str, *, limit: int = 30) -> list[EvidenceItem]:
    """Retrieve recent evidence for a ticker (plan §9.6), newest first."""
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {_EVIDENCE_SELECT_COLUMNS} FROM news.extracted_evidence "
            "WHERE ticker = %s ORDER BY published_at DESC NULLS LAST LIMIT %s",
            (ticker, limit),
        )
        return [_row_to_evidence(row) for row in cur.fetchall()]


def get_evidence_for_run(conn, research_run_id: str, *, limit: int = 30) -> list[EvidenceItem]:
    """Retrieve evidence linked to a research run via its selected articles."""
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {_EVIDENCE_SELECT_COLUMNS} FROM news.extracted_evidence e "
            "JOIN news.research_run_articles ra ON ra.article_id = e.article_id "
            "WHERE ra.research_run_id = %s ORDER BY e.published_at DESC NULLS LAST LIMIT %s",
            (research_run_id, limit),
        )
        return [_row_to_evidence(row) for row in cur.fetchall()]


def save_editor_output(
    conn,
    research_run_id: str,
    *,
    report_markdown: str,
    title: str | None = None,
    citation_count: int = 0,
    status: str = "draft",
) -> int:
    """Insert a news.editor_outputs row. Returns its id."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO news.editor_outputs
                (research_run_id, title, report_markdown, citation_count, status)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (research_run_id, title, report_markdown, citation_count, status),
        )
        return cur.fetchone()[0]


def mark_run_status(
    conn,
    research_run_id: str,
    status: str,
    *,
    error_message: str | None = None,
    finished: bool = False,
) -> None:
    """Update a research run's status (running|completed|failed|needs_review)."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE news.research_runs SET status = %s, error_message = %s, "
            "finished_at = CASE WHEN %s THEN NOW() ELSE finished_at END "
            "WHERE research_run_id = %s",
            (status, error_message, finished, research_run_id),
        )
