from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from backend.database.canonical.connection import get_conn
from backend.database.canonical.source_dal import (
    compute_source_doc_id,
    upsert_source_document,
)

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

# Map legacy/connector source_type values to the CHECK constraint set on
# ingest.source_documents.source_type.  Any value not in this map is left
# unchanged (already valid, or will be rejected by the DB with a clear error).
_SOURCE_TYPE_MAP: dict[str, str] = {
    "financial_statement": "vnstock_financial",
    "disclosure": "exchange_disclosure",
    "regulatory_filing": "regulatory_notice",
    "regulatory": "regulatory_notice",
    "tender": "exchange_disclosure",
    "bidding": "exchange_disclosure",
    "market_reference": "vnstock_financial",
    "audited_financial_statement": "audited_financial_statement",
}


def _tier_for_source_type(source_type: str) -> int:
    return _SOURCE_TYPE_TIER.get(source_type, 3)


def _canonical_source_type(source_type: str) -> str:
    """Map legacy connector source_type values to canonical ingest.source_documents constraint."""
    return _SOURCE_TYPE_MAP.get(source_type, source_type)


def _parse_published_at(published_at: str | None) -> datetime | None:
    """Parse an ISO-8601 string or date string to a timezone-aware datetime."""
    if not published_at:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(published_at, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt
        except ValueError:
            continue
    return None


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
    def __init__(self, store: Any = None) -> None:
        # store parameter kept for backward compatibility; writes go through canonical DAL.
        pass

    @staticmethod
    def compute_checksum(payload: bytes) -> str:
        return hashlib.sha256(payload).hexdigest()

    @staticmethod
    def compute_source_id(logical_id: str, source_uri: str, checksum: str) -> str:
        """Kept for backward compat. Returns SHA256(logical_id|source_uri|checksum)."""
        raw = f"{logical_id}|{source_uri}|{checksum}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    # Backward-compatibility alias.
    @staticmethod
    def compute_version_id(source_id: str, source_uri: str, checksum: str) -> str:
        return SourceRegistry.compute_source_id(source_id, source_uri, checksum)

    def get_latest_by_uri(self, logical_id: str, source_uri: str) -> tuple[str, str] | None:
        """Return (source_doc_id, checksum) of the most-recently ingested source for this URI."""
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT source_doc_id, checksum
                    FROM ingest.source_documents
                    WHERE source_uri = %s
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (source_uri,),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return row[0], row[1]

    # Catalog source types that should be upserted (not versioned) — only the
    # latest payload per (ticker, logical_id, source_type) is kept.
    _CATALOG_TYPES = frozenset({"vnstock_company"})

    def register_source(self, data: SourceInput) -> str:
        """Upsert a source document into ingest.source_documents. Returns source_doc_id."""
        resolved_tier = (
            data.source_tier
            if data.source_tier is not None
            else _tier_for_source_type(data.source_type)
        )
        canonical_type = _canonical_source_type(data.source_type)
        return upsert_source_document(
            ticker=data.ticker,
            source_type=canonical_type,
            source_tier=resolved_tier,
            source_uri=data.source_uri,
            checksum=data.checksum,
            source_title=data.source_title,
            published_at=_parse_published_at(data.published_at),
            fiscal_year=data.fiscal_year,
            fiscal_period=data.fiscal_period,
            connector_version=data.connector_version,
            metadata={
                "logical_id": data.logical_id,
                "reliability_tier": data.reliability_tier,
                # Local raw-snapshot path kept for lineage only. Per migration 030
                # (Supabase Storage contract) the storage_path column holds a Storage
                # object key paired with storage_bucket, never a local filesystem path.
                "raw_path": data.raw_path,
                **data.metadata_json,
            },
        )

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
        """Record raw payload lineage in ingest.source_documents.

        Updates the source document record with payload location and connector
        provenance.  ingest.raw_payloads was removed in migration 026; lineage
        is now carried in metadata_json on the source document itself.
        """
        if not source_id:
            return
        payload_meta: dict[str, Any] = {
            "raw_payload_content_type": content_type,
            "raw_payload_checksum": checksum,
        }
        if storage_path:
            payload_meta["raw_payload_path"] = storage_path
        if connector_name:
            payload_meta["raw_connector_name"] = connector_name
        if connector_version:
            payload_meta["raw_connector_version"] = connector_version
        if request_uri:
            payload_meta["raw_request_uri"] = request_uri
        if response_path:
            payload_meta["raw_response_path"] = response_path
        if response_checksum:
            payload_meta["raw_response_checksum"] = response_checksum

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE ingest.source_documents
                    SET metadata_json  = metadata_json || %s::jsonb,
                        fetch_status   = CASE WHEN fetch_status = 'registered'
                                              THEN 'fetched'
                                              ELSE fetch_status END
                    WHERE source_doc_id = %s
                    """,
                    (
                        __import__("json").dumps(payload_meta),
                        source_id,
                    ),
                )

    def register_parser_run(
        self,
        source_id: str,
        parser_name: str,
        parser_version: str,
    ) -> str:
        """Insert a connector run record in 'running' state. Returns run_id (str)."""
        run_id = f"parser_{uuid.uuid4().hex[:16]}"
        with get_conn() as conn:
            with conn.cursor() as cur:
                # Resolve ticker from the source document if available.
                cur.execute(
                    "SELECT ticker FROM ingest.source_documents WHERE source_doc_id = %s",
                    (source_id,),
                )
                row = cur.fetchone()
                ticker = row[0] if row else None
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ingest.connector_runs
                        (run_id, ticker, connector_name, status, stats_json)
                    VALUES (%s, %s, %s, 'running',
                            jsonb_build_object(
                                'parser_version', %s,
                                'source_doc_id',  %s
                            ))
                    ON CONFLICT (run_id) DO NOTHING
                    """,
                    (run_id, ticker, parser_name, parser_version, source_id),
                )
        return run_id

    def complete_parser_run(
        self,
        parser_run_id: str | int,
        rows_extracted: int = 0,
        error_message: str | None = None,
    ) -> None:
        """Mark a connector run as completed or failed."""
        status = "failed" if error_message else "completed"
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE ingest.connector_runs
                    SET status               = %s,
                        finished_at          = NOW(),
                        observations_created = %s,
                        error_message        = %s
                    WHERE run_id = %s
                    """,
                    (status, rows_extracted, error_message, str(parser_run_id)),
                )

    def save_raw_snapshot(self, payload: bytes, out_path: Path) -> str:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(payload)
        checksum = self.compute_checksum(payload)
        out_path.with_suffix(out_path.suffix + ".sha256").write_text(checksum, encoding="utf-8")
        return checksum
