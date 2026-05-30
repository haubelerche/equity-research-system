"""Catalyst event linker — Phase 4 of the Data Trust Layer.

Links catalyst events from `fact.catalyst_events` to fiscal periods.
Every event receives `causality_level = contextual_event` by default.

Causality levels (see plan taxonomy):
  contextual_event          — event occurred in same period; no causality proven
  potential_driver          — plausible but not confirmed
  management_disclosed_driver — company explicitly stated this driver
  validated_driver          — independent numeric evidence confirms causal link

Only `management_disclosed_driver` and `validated_driver` may generate causal
language in reports. The other two levels must use hedged wording only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any


_CAUSALITY_LEVELS = frozenset({
    "contextual_event",
    "potential_driver",
    "management_disclosed_driver",
    "validated_driver",
})

# Wording templates enforced by the report generator
CAUSALITY_WORDING: dict[str, str] = {
    "contextual_event": "diễn ra trong bối cảnh",
    "potential_driver": "có thể là một yếu tố hỗ trợ",
    "management_disclosed_driver": "theo công ty, biến động này đến từ",
    "validated_driver": "được hỗ trợ bởi",
}

# Causal language patterns that must NOT appear with contextual_event or potential_driver
CAUSAL_PATTERNS: list[str] = [
    r"\bdo\b",
    r"\bkhiến\b",
    r"\bbởi vì\b",
    r"\bdẫn đến\b",
    r"\bresulted from\b",
    r"\bcaused by\b",
    r"\bbecause of\b",
    r"\bowing to\b",
    r"\bdue to\b",
    r"\bdriven by\b",
]


@dataclass
class CatalystEventEntry:
    """A catalyst event linked to a fiscal period."""
    event_id: str
    ticker: str | None
    event_type: str
    title: str
    summary: str | None
    occurred_at: str
    materiality_hint: str | None
    source_url: str | None
    source_id: str
    causality_level: str = "contextual_event"
    fiscal_period_overlap: str | None = None
    allowed_wording: str = field(init=False)

    def __post_init__(self) -> None:
        if self.causality_level not in _CAUSALITY_LEVELS:
            self.causality_level = "contextual_event"
        self.allowed_wording = CAUSALITY_WORDING.get(
            self.causality_level, "diễn ra trong bối cảnh"
        )


def _fy_window(fiscal_year: int) -> tuple[datetime, datetime]:
    """Return (start, end) datetime window for a fiscal year ±6 months."""
    start = datetime(fiscal_year, 1, 1, tzinfo=UTC) - timedelta(days=180)
    end = datetime(fiscal_year, 12, 31, tzinfo=UTC) + timedelta(days=180)
    return start, end


def link_events_to_periods(
    ticker: str,
    periods: list[str],
    db_facts: list[dict[str, Any]] | None = None,
) -> dict[str, list[CatalystEventEntry]]:
    """Link catalyst events to fiscal periods for a ticker.

    Events are linked when their `occurred_at` falls within ±6 months of the
    fiscal year end. All events receive `causality_level = contextual_event`
    by default — callers or analysts must upgrade the level explicitly.

    Args:
        ticker: Ticker symbol.
        periods: List of FY period strings (e.g. ["2021FY", "2023FY"]).
        db_facts: Optional pre-loaded catalyst event dicts (for testing without DB).
            If None, queries `fact.catalyst_events` via PostgresFactStore.

    Returns:
        dict mapping period → list[CatalystEventEntry], sorted by occurred_at.
    """
    result: dict[str, list[CatalystEventEntry]] = {p: [] for p in periods}

    rows = db_facts
    if rows is None:
        rows = _load_from_db(ticker)

    for row in rows:
        oat_raw = row.get("occurred_at")
        if oat_raw is None:
            continue
        if isinstance(oat_raw, str):
            try:
                oat = datetime.fromisoformat(oat_raw.replace("Z", "+00:00"))
            except ValueError:
                continue
        elif isinstance(oat_raw, datetime):
            oat = oat_raw
        else:
            continue

        if oat.tzinfo is None:
            oat = oat.replace(tzinfo=UTC)

        for period in periods:
            try:
                fy = int(period[:4])
            except ValueError:
                continue
            start, end = _fy_window(fy)
            if start <= oat <= end:
                # Use DB-stored causality_level if available; default to contextual_event
                cl = row.get("causality_level") or "contextual_event"
                if cl not in _CAUSALITY_LEVELS:
                    cl = "contextual_event"
                entry = CatalystEventEntry(
                    event_id=str(row.get("event_id", "")),
                    ticker=row.get("ticker") or ticker,
                    event_type=str(row.get("event_type", "other")),
                    title=str(row.get("title", "")),
                    summary=row.get("summary"),
                    occurred_at=oat.isoformat(),
                    materiality_hint=row.get("materiality_hint"),
                    source_url=row.get("source_url"),
                    source_id=str(row.get("source_id", "")),
                    causality_level=cl,
                    fiscal_period_overlap=period,
                )
                result[period].append(entry)

    # Sort each period's events by occurred_at, most recent first
    for period in result:
        result[period].sort(key=lambda e: e.occurred_at, reverse=True)

    return result


def _load_from_db(ticker: str) -> list[dict[str, Any]]:
    """Load catalyst events for a ticker from the database."""
    import os
    import psycopg2
    import psycopg2.extras
    dsn = os.getenv("DATABASE_URL", "")
    if not dsn:
        return []
    try:
        conn = psycopg2.connect(dsn)
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT event_id, ticker, event_type, title, summary,
                       occurred_at, materiality_hint, source_url, source_id,
                       causality_level
                FROM fact.catalyst_events
                WHERE (ticker = %s OR ticker IS NULL)
                  AND validation_status != 'rejected'
                ORDER BY occurred_at DESC
                LIMIT 500
                """,
                (ticker,),
            )
            return [dict(r) for r in cur.fetchall()]
    except Exception:  # noqa: BLE001
        return []
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
