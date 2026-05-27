from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scripts.db.fact_store import PostgresFactStore


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

    def register_source(self, data: SourceInput) -> str:
        """Insert a source record into ingest.sources. Returns source_id."""
        source_id = self.compute_source_id(data.logical_id, data.source_uri, data.checksum)
        import psycopg2.extras as _extras
        with self.store.conn() as connection:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ingest.sources
                    (source_id, logical_id, ticker, source_type, source_uri, source_title,
                     published_at, fiscal_year, fiscal_period, reliability_tier,
                     connector_version, checksum, raw_path, metadata_json)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
    ) -> None:
        """Insert a raw payload record into ingest.raw_payloads."""
        import psycopg2.extras as _extras
        with self.store.conn() as connection:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ingest.raw_payloads
                    (source_id, content_type, payload_json, payload_text, storage_path, checksum)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        source_id,
                        content_type,
                        _extras.Json(payload_json) if payload_json is not None else None,
                        payload_text,
                        storage_path,
                        checksum,
                    ),
                )

    def save_raw_snapshot(self, payload: bytes, out_path: Path) -> str:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(payload)
        checksum = self.compute_checksum(payload)
        out_path.with_suffix(out_path.suffix + ".sha256").write_text(checksum, encoding="utf-8")
        return checksum
