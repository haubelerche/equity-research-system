"""Render a ticker's report + explanation and store them durably for download.

The deployed web app runs on an ephemeral filesystem, so rendered PDFs must be
uploaded to Supabase Storage (the ``exports`` bucket) to survive container
restarts. Both the fast-render path and the full-pipeline completion hook call
:func:`render_and_store`, so downloads behave identically regardless of how the
report was produced.
"""
from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

# Imported at module level so tests can patch the renderer functions.
from backend.reporting.final_report_renderer import (
    render_client_report_to_directory,
    render_report_explanation_to_directory,
)
from backend.storage import EXPORTS_BUCKET, SupabaseStorageAdapter, client_report_key


def latest_renderable_run_id(ticker: str) -> str | None:
    """Newest run for *ticker* that has artifacts a report can be rendered from.

    Drives the fast-vs-full routing: a non-None result means we can render
    immediately instead of running the whole pipeline.
    """
    from backend.database.config import connect_with_retry, require_database_url

    with connect_with_retry(require_database_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT a.run_id
                FROM research.run_artifacts a
                JOIN research.runs r ON r.run_id = a.run_id
                WHERE r.ticker = %s
                  AND a.section_key IN (
                    'publishable_final_report_model',
                    'review_passed_report_model',
                    'report_candidate_model',
                    'valuation'
                  )
                ORDER BY r.created_at DESC
                LIMIT 1
                """,
                (ticker.upper(),),
            )
            row = cur.fetchone()
    return row[0] if row else None


@dataclass(frozen=True)
class StoredReport:
    ticker: str
    run_id: str
    report_key: str
    explanation_key: str


def render_and_store(
    ticker: str,
    run_id: str,
    *,
    mode: str = "standard",
    storage: SupabaseStorageAdapter | None = None,
) -> StoredReport:
    """Render the report + explanation for *run_id* and upload both to exports.

    Returns the ticker-stable storage keys. Rendering happens in a temp dir;
    nothing is left on the local filesystem. Upserts so the newest render
    always wins for the ticker.
    """
    ticker = ticker.upper()
    storage = storage or SupabaseStorageAdapter()
    report_key = client_report_key(ticker, "report.pdf")
    explanation_key = client_report_key(ticker, "explanation.pdf")

    with tempfile.TemporaryDirectory(prefix=f"render-{run_id}-") as temp_dir:
        _html, pdf_path, view_model = render_client_report_to_directory(
            run_id=run_id,
            ticker=ticker,
            mode=mode,
            output_dir=temp_dir,
        )
        _exp_html, exp_pdf = render_report_explanation_to_directory(
            run_id=run_id,
            ticker=ticker,
            view_model=view_model,
            output_dir=temp_dir,
        )
        storage.upload_file(EXPORTS_BUCKET, report_key, pdf_path, "application/pdf", upsert=True)
        storage.upload_file(EXPORTS_BUCKET, explanation_key, exp_pdf, "application/pdf", upsert=True)

    return StoredReport(
        ticker=ticker,
        run_id=run_id,
        report_key=report_key,
        explanation_key=explanation_key,
    )
