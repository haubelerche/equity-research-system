"""Canonical DAL: report â€” report objects, claims, citations, gate results.

This module populates the previously-empty report.* tables (now report.*).
Every quantitative claim must be recorded here before export approval.

Write permission: report generation pipeline.
Read permission: export gate, HITL approval workflow.

LLM-generated text is written via claim.claim_text â€” but values are always
sourced from locked canonical facts, never from LLM output.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

import psycopg2.extras

from backend.database.canonical.audit_dal import log_event
from backend.database.canonical.connection import get_conn


def _claim_id(report_id: str, section: str, metric: str, period: str, value: float | None) -> str:
    raw = f"{report_id}|{section}|{metric}|{period}|{value}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _report_id(ticker: str, run_id: str, report_mode: str) -> str:
    raw = f"{ticker}|{run_id}|{report_mode}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def create_or_update_report(
    ticker: str,
    run_id: str,
    report_mode: str = "analyst_draft",
    report_type: str = "full_report",
    status: str = "draft",
    html_artifact_id: str | None = None,
    pdf_artifact_id: str | None = None,
) -> str:
    """Create or update a report record. Returns report_id."""
    report_id = _report_id(ticker, run_id, report_mode)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO report.reports (
                    report_id, run_id, ticker, report_type, report_mode, status,
                    html_artifact_id, pdf_artifact_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (report_id) DO UPDATE
                SET status           = EXCLUDED.status,
                    html_artifact_id = COALESCE(EXCLUDED.html_artifact_id, report.reports.html_artifact_id),
                    pdf_artifact_id  = COALESCE(EXCLUDED.pdf_artifact_id, report.reports.pdf_artifact_id),
                    updated_at       = NOW()
                """,
                (report_id, run_id, ticker, report_type, report_mode, status,
                 html_artifact_id, pdf_artifact_id),
            )
    return report_id


def record_claims(report_id: str, ticker: str, claims: list[dict[str, Any]]) -> int:
    """Batch-insert report claims. Returns number inserted.

    Each claim dict: section, claim_text, claim_type, period, metric, value_mentioned, unit.
    """
    payload = [
        (
            _claim_id(report_id, c.get("section",""), c.get("metric",""), c.get("period",""), c.get("value_mentioned")),
            report_id,
            c.get("section"),
            c.get("claim_text"),
            c.get("claim_type", "quantitative"),
            ticker,
            c.get("period"),
            c.get("metric"),
            c.get("value_mentioned"),
            c.get("unit"),
        )
        for c in claims
    ]
    if not payload:
        return 0
    with get_conn() as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO report.claims (
                    claim_id, report_id, section, claim_text, claim_type,
                    ticker, period, metric, value_mentioned, unit
                )
                VALUES %s
                ON CONFLICT (claim_id) DO NOTHING
                """,
                payload,
            )
    return len(payload)


def record_citation(
    claim_id: str,
    fact_id: str | None = None,
    source_doc_id: str | None = None,
    support_type: str = "direct_value",
    source_tier: int | None = None,
) -> str:
    """Record one citation linking a claim to a canonical fact and/or source document."""
    raw = f"{claim_id}|{fact_id}|{source_doc_id}"
    citation_id = hashlib.sha256(raw.encode()).hexdigest()[:32]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO report.citation_records (
                    citation_id, claim_id, fact_id, source_doc_id,
                    support_type, source_tier, validation_status
                )
                VALUES (%s, %s, %s, %s, %s, %s, 'unverified')
                ON CONFLICT DO NOTHING
                """,
                (citation_id, claim_id, fact_id, source_doc_id, support_type, source_tier),
            )
    return citation_id


def record_gate_result(
    report_id: str,
    gate_name: str,
    status: str,
    severity: str = "medium",
    issues: list[dict] | None = None,
) -> None:
    """Upsert a quality gate result for a report."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO report.gate_results (
                    report_id, gate_name, status, severity, issue_count, issues_json
                )
                VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (report_id, gate_name) DO UPDATE
                SET status      = EXCLUDED.status,
                    severity    = EXCLUDED.severity,
                    issue_count = EXCLUDED.issue_count,
                    issues_json = EXCLUDED.issues_json
                """,
                (
                    report_id, gate_name, status, severity,
                    len(issues or []),
                    json.dumps(issues or []),
                ),
            )


def get_uncited_quantitative_claims(report_id: str) -> list[dict[str, Any]]:
    """Return quantitative claims with no citation. Blocks export approval if non-empty."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT report_id, claim_id, claim_text
                FROM report.uncited_quantitative_claims
                WHERE report_id = %s
                """,
                (report_id,),
            )
            cols = [d.name for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]


def approve_report(
    report_id: str,
    approval_type: str,
    approved_by: str,
    comment: str | None = None,
) -> None:
    """Record HITL approval for a report stage."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO report.approval_records (
                    report_id, approval_type, status, approved_by, approved_at, comment
                )
                VALUES (%s, %s, 'approved', %s, NOW(), %s)
                """,
                (report_id, approval_type, approved_by, comment),
            )
    log_event(
        event_type="approval",
        actor=approved_by,
        target_table="report.reports",
        target_id=report_id,
        payload={"approval_type": approval_type, "comment": comment},
    )

