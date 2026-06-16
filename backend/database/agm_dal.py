"""DAL for research.agm_resolutions — AGM (ĐHCĐ) driver packs (one per ticker-meeting).

Written offline by scripts/ingest_agm.py (from the ĐHCĐ PDFs) and read by the forecast
path (backend.harness.tools) as priority forward drivers. Connection is injectable
(`conn=`) so serialization/selection logic is unit-testable. Mirrors company_evidence_dal.
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


def upsert_agm_resolutions(
    ticker: str,
    meeting_year: int,
    agm_pack: dict[str, Any],
    *,
    source_docs: list[dict[str, Any]] | None = None,
    model: str | None = None,
    conn: Any = None,
) -> None:
    """Insert or replace the AGM pack for (ticker, meeting_year). Idempotent."""
    pack_json = json.dumps(agm_pack or {}, ensure_ascii=False)
    docs_json = json.dumps(source_docs or [], ensure_ascii=False)
    with _conn_ctx(conn) as c:
        with c.cursor() as cur:
            cur.execute(
                """
                INSERT INTO research.agm_resolutions
                    (ticker, meeting_year, agm_pack, source_docs, model, updated_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
                ON CONFLICT (ticker, meeting_year) DO UPDATE
                SET agm_pack    = EXCLUDED.agm_pack,
                    source_docs = EXCLUDED.source_docs,
                    model       = EXCLUDED.model,
                    updated_at  = NOW()
                """,
                (ticker.upper(), int(meeting_year), pack_json, docs_json, model),
            )


def load_latest_agm(ticker: str, *, conn: Any = None) -> dict[str, Any]:
    """Return the most recent meeting's AGM pack for *ticker*, or {} if none."""
    with _conn_ctx(conn) as c:
        with c.cursor() as cur:
            cur.execute(
                """
                SELECT agm_pack
                FROM research.agm_resolutions
                WHERE ticker = %s
                ORDER BY meeting_year DESC
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
