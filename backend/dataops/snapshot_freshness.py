"""Find the latest ready (fresh + active) canonical snapshot for a ticker (read-only)."""
from __future__ import annotations
from datetime import datetime, timedelta, UTC
from typing import Any
from backend.database.config import connect_with_retry, require_database_url


def is_fresh(snapshot: dict[str, Any] | None, ttl_hours: int) -> bool:
    """True if snapshot exists, status is 'active', and created_at is within ttl_hours."""
    if not snapshot or snapshot.get("status") != "active":
        return False
    created = snapshot.get("created_at")
    if created is None:
        return False
    if getattr(created, "tzinfo", None) is None:
        created = created.replace(tzinfo=UTC)
    return datetime.now(UTC) - created <= timedelta(hours=ttl_hours)


def latest_ready_snapshot(ticker: str, ttl_hours: int = 24) -> dict[str, Any] | None:
    """Return the newest active snapshot row for *ticker* if fresh, else None."""
    with connect_with_retry(require_database_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT snapshot_id, ticker, status, created_at, facts_count "
                "FROM research.snapshots "
                "WHERE ticker = %s AND status = 'active' "
                "ORDER BY created_at DESC LIMIT 1",
                (ticker.upper(),),
            )
            row = cur.fetchone()
    if not row:
        return None
    snap = {
        "snapshot_id": row[0], "ticker": row[1], "status": row[2],
        "created_at": row[3], "facts_count": row[4],
    }
    return snap if is_fresh(snap, ttl_hours) else None
