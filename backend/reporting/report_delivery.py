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
from backend.reporting.pdf_quality_gate import is_client_pdf_safe, require_client_pdf_safe
from backend.storage import EXPORTS_BUCKET, SupabaseStorageAdapter, client_report_key


def existing_client_report_available(
    ticker: str,
    *,
    storage: SupabaseStorageAdapter | None = None,
    output_dir: str | Path = "output",
) -> bool:
    """Return True when a downloadable report already exists for *ticker*.

    Fast-render is an optimization over an existing renderable run. If re-rendering
    fails because the run-scoped artifacts are unavailable locally, an existing
    ticker-stable export should remain downloadable instead of turning the UI run
    into a hard failure.
    """
    ticker = ticker.upper()
    try:
        adapter = storage or SupabaseStorageAdapter()
        if adapter.exists(EXPORTS_BUCKET, client_report_key(ticker, "report.pdf")):
            return True
    except Exception:
        pass

    local_report = Path(output_dir) / f"{ticker}_report.pdf"
    return is_client_pdf_safe(local_report)


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
                WITH run_sections AS (
                    SELECT
                        r.run_id,
                        r.created_at,
                        BOOL_OR(a.section_key IN (
                            'publishable_final_report_model',
                            'review_passed_report_model',
                            'report_candidate_model'
                        )) AS has_final_model,
                        BOOL_OR(a.section_key = 'facts' AND a.storage_path IS NOT NULL) AS has_facts,
                        BOOL_OR(a.section_key = 'valuation' AND a.storage_path IS NOT NULL) AS has_valuation,
                        BOOL_OR(a.section_key = 'manifest' AND a.storage_path IS NOT NULL) AS has_manifest
                    FROM research.runs r
                    JOIN research.run_artifacts a ON a.run_id = r.run_id
                    WHERE r.ticker = %s
                    GROUP BY r.run_id, r.created_at
                )
                SELECT run_id
                FROM run_sections
                WHERE has_final_model OR (has_facts AND has_valuation AND has_manifest)
                ORDER BY
                    CASE WHEN has_final_model THEN 0 ELSE 1 END,
                    created_at DESC
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
        require_client_pdf_safe(pdf_path)
        require_client_pdf_safe(exp_pdf)
        storage.upload_file(EXPORTS_BUCKET, report_key, pdf_path, "application/pdf", upsert=True)
        storage.upload_file(EXPORTS_BUCKET, explanation_key, exp_pdf, "application/pdf", upsert=True)

    return StoredReport(
        ticker=ticker,
        run_id=run_id,
        report_key=report_key,
        explanation_key=explanation_key,
    )
