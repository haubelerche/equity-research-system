from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scripts.db.fact_store import PostgresFactStore

# Policy-driven source_tier defaults by source_type.
# Connectors may override by passing source_tier explicitly.
# Tier 0: audited exchange filings, regulatory documents
# Tier 1: company IR, manual uploads
# Tier 2: reputable media, industry reports, news
# Tier 3: API aggregators (vnstock), scrapers, tender feeds
_SOURCE_TYPE_TIER: dict[str, int] = {
    "annual_report": 0,
    "disclosure": 0,
    "regulatory_filing": 0,
    "news": 2,
    "industry_report": 2,
    "manual": 1,
    "vnstock_financial": 3,
    "vnstock_price": 3,
    "vnstock_company": 3,
    "financial_statement": 3,
    "market_reference": 3,
    "tender": 3,
    "bidding": 3,
    "regulatory": 3,
}


def _tier_for_source_type(source_type: str) -> int:
    return _SOURCE_TYPE_TIER.get(source_type, 3)


@dataclass(frozen=True)
class SourceInput:
    logical_id: str
    source_uri: str
    source_type: str
    checksum: str
    connector_version: str
    ticker: str | None = None
    raw_path: str | None = None
    published_at: str | None = None
    fiscal_year: int | None = None
    fiscal_period: str | None = None
    source_title: str | None = None
    reliability_tier: int = 2
    # source_tier uses the 0-4 taxonomy from the Data Trust Layer plan.
    # If None, derived automatically from source_type via _tier_for_source_type().
    source_tier: int | None = None
    metadata_json: dict[str, Any] = field(default_factory=dict)


# Backward-compatibility alias — callers using SourceVersionInput continue to work.
SourceVersionInput = SourceInput


class SourceRegistry:
    def __init__(self, store: PostgresFactStore | None = None) -> None:
        self.store = store or PostgresFactStore()

    @staticmethod
    def compute_checksum(payload: bytes) -> str:
        return hashlib.sha256(payload).hexdigest()

    @staticmethod
    def compute_source_id(logical_id: str, source_uri: str, checksum: str) -> str:
        raw = f"{logical_id}|{source_uri}|{checksum}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    # Backward-compatibility alias.
    @staticmethod
    def compute_version_id(source_id: str, source_uri: str, checksum: str) -> str:
        return SourceRegistry.compute_source_id(source_id, source_uri, checksum)

    def get_latest_by_uri(self, logical_id: str, source_uri: str) -> tuple[str, str] | None:
        """Return (source_id, checksum) of the most-recently ingested source for this URI."""
        with self.store.conn() as connection:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    SELECT source_id, checksum
                    FROM ingest.sources
                    WHERE logical_id = %s AND source_uri = %s
                    ORDER BY ingested_at DESC
                    LIMIT 1
                    """,
                    (logical_id, source_uri),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return row[0], row[1]

    # Catalog source types that should be upserted (not versioned) — only the
    # latest payload per (ticker, logical_id, source_type) is kept.
    _CATALOG_TYPES = frozenset({"vnstock_company"})

    def register_source(self, data: SourceInput) -> str:
        """Insert or upsert a source record into ingest.sources. Returns source_id."""
        source_id = self.compute_source_id(data.logical_id, data.source_uri, data.checksum)
        resolved_tier = (
            data.source_tier
            if data.source_tier is not None
            else _tier_for_source_type(data.source_type)
        )
        import psycopg2.extras as _extras
        with self.store.conn() as connection:
            with connection.cursor() as cur:
                if data.source_type in self._CATALOG_TYPES:
                    # Catalog-type upsert: only one live row per (ticker, logical_id,
                    # source_type) is kept, but we MUST NOT update source_id (the PK)
                    # because other tables (raw_payloads) hold FK references to it.
                    # Strategy:
                    #   INSERT new row; on conflict, update metadata fields only (not PK).
                    #   RETURNING source_id gives back whichever row is now live — the
                    #   newly-inserted one OR the existing one whose PK was preserved.
                    cur.execute(
                        """
                        INSERT INTO ingest.sources
                        (source_id, logical_id, ticker, source_type, source_uri, source_title,
                         published_at, fiscal_year, fiscal_period, reliability_tier,
                         source_tier, connector_version, checksum, raw_path, metadata_json)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (ticker, logical_id, source_type)
                            WHERE source_type = 'vnstock_company'
                        DO UPDATE SET
                            source_uri        = EXCLUDED.source_uri,
                            checksum          = EXCLUDED.checksum,
                            raw_path          = EXCLUDED.raw_path,
                            connector_version = EXCLUDED.connector_version,
                            source_tier       = EXCLUDED.source_tier,
                            ingested_at       = NOW()
                        RETURNING source_id
                        """,
                        (
                            source_id,
                            data.logical_id,
                            data.ticker,
                            data.source_type,
                            data.source_uri,
                            data.source_title,
                            data.published_at,
                            data.fiscal_year,
                            data.fiscal_period,
                            data.reliability_tier,
                            resolved_tier,
                            data.connector_version,
                            data.checksum,
                            data.raw_path,
                            _extras.Json(data.metadata_json),
                        ),
                    )
                    # Use the actual source_id that survived the upsert (may differ
                    # from the computed one if a pre-existing row was kept).
                    returned = cur.fetchone()
                    if returned:
                        source_id = returned[0]
                else:
                    # All other source types are version-tracked: each unique
                    # (logical_id, source_uri, checksum) creates its own row.
                    cur.execute(
                        """
                        INSERT INTO ingest.sources
                        (source_id, logical_id, ticker, source_type, source_uri, source_title,
                         published_at, fiscal_year, fiscal_period, reliability_tier,
                         source_tier, connector_version, checksum, raw_path, metadata_json)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (source_id) DO NOTHING
                        """,
                        (
                            source_id,
                            data.logical_id,
                            data.ticker,
                            data.source_type,
                            data.source_uri,
                            data.source_title,
                            data.published_at,
                            data.fiscal_year,
                            data.fiscal_period,
                            data.reliability_tier,
                            resolved_tier,
                            data.connector_version,
                            data.checksum,
                            data.raw_path,
                            _extras.Json(data.metadata_json),
                        ),
                    )
        return source_id

    # Backward-compatibility alias — callers using register_version continue to work.
    def register_version(self, data: SourceInput) -> str:
        return self.register_source(data)

    def register_raw_payload(
        self,
        source_id: str,
        content_type: str,
        checksum: str,
        payload_json: Any = None,
        payload_text: str | None = None,
        storage_path: str | None = None,
        connector_name: str | None = None,
        connector_version: str | None = None,
        request_uri: str | None = None,
        request_params: dict[str, Any] | None = None,
        response_path: str | None = None,
        response_checksum: str | None = None,
    ) -> None:
        """Insert a raw payload record into ingest.raw_payloads.

        The new connector_* and request_* parameters populate the columns added
        in migration 010, enabling full Gate 2 lineage traversal.
        """
        import psycopg2.extras as _extras
        with self.store.conn() as connection:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ingest.raw_payloads
                    (source_id, content_type, payload_json, payload_text,
                     storage_path, checksum,
                     connector_name, connector_version, request_uri,
                     request_params, response_path, response_checksum)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        source_id,
                        content_type,
                        _extras.Json(payload_json) if payload_json is not None else None,
                        payload_text,
                        storage_path,
                        checksum,
                        connector_name,
                        connector_version,
                        request_uri,
                        _extras.Json(request_params) if request_params is not None else None,
                        response_path,
                        response_checksum,
                    ),
                )

    def register_parser_run(
        self,
        source_id: str,
        parser_name: str,
        parser_version: str,
    ) -> int:
        """Insert a parser_run record in 'running' state. Returns parser_run_id."""
        with self.store.conn() as connection:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ingest.parser_runs
                    (source_id, parser_name, parser_version, status)
                    VALUES (%s, %s, %s, 'running')
                    RETURNING parser_run_id
                    """,
                    (source_id, parser_name, parser_version),
                )
                return cur.fetchone()[0]

    def complete_parser_run(
        self,
        parser_run_id: int,
        rows_extracted: int = 0,
        error_message: str | None = None,
    ) -> None:
        """Mark a parser_run as completed or failed."""
        status = "failed" if error_message else "completed"
        with self.store.conn() as connection:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    UPDATE ingest.parser_runs
                    SET status = %s, completed_at = NOW(),
                        rows_extracted = %s, error_message = %s
                    WHERE parser_run_id = %s
                    """,
                    (status, rows_extracted, error_message, parser_run_id),
                )

    def save_raw_snapshot(self, payload: bytes, out_path: Path) -> str:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(payload)
        checksum = self.compute_checksum(payload)
        out_path.with_suffix(out_path.suffix + ".sha256").write_text(checksum, encoding="utf-8")
        return checksum
