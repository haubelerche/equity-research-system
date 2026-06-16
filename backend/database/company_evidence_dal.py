"""DAL for research.company_evidence — qualitative evidence packs (one per ticker-year).

Written offline by scripts/ingest_pdf_llm.py (from the annual-report PDF) and read
by the run's INGEST stage into state.artifacts["evidence_pack"]. Connection is
injectable (`conn=`) so the serialization/selection logic is unit-testable.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any


@contextmanager
def _conn_ctx(conn: Any):
    if conn is not None:
        yield conn
        return
    from backend.database.canonical.connection import get_conn

    with get_conn() as real:
        yield real


def upsert_company_evidence(
    ticker: str,
    fiscal_year: int,
    evidence_pack: dict[str, Any],
    *,
    source_doc_id: str | None = None,
    model: str | None = None,
    conn: Any = None,
) -> None:
    """Insert or replace the evidence pack for (ticker, fiscal_year). Idempotent."""
    payload = json.dumps(evidence_pack or {}, ensure_ascii=False)
    with _conn_ctx(conn) as c:
        with c.cursor() as cur:
            cur.execute(
                """
                INSERT INTO research.company_evidence
                    (ticker, fiscal_year, evidence_pack, source_doc_id, model, updated_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
                ON CONFLICT (ticker, fiscal_year) DO UPDATE
                SET evidence_pack = EXCLUDED.evidence_pack,
                    source_doc_id = EXCLUDED.source_doc_id,
                    model         = EXCLUDED.model,
                    updated_at    = NOW()
                """,
                (ticker.upper(), int(fiscal_year), payload, source_doc_id, model),
            )


def load_latest_company_evidence(ticker: str, *, conn: Any = None) -> dict[str, Any]:
    """Return the most recent year's evidence pack for *ticker*, or {} if none."""
    with _conn_ctx(conn) as c:
        with c.cursor() as cur:
            cur.execute(
                """
                SELECT evidence_pack
                FROM research.company_evidence
                WHERE ticker = %s
                ORDER BY fiscal_year DESC
                LIMIT 1
                """,
                (ticker.upper(),),
            )
            row = cur.fetchone()
    if not row or row[0] is None:
        return {}
    pack = row[0]
    if isinstance(pack, dict):
        return pack
    try:
        parsed = json.loads(pack)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}
