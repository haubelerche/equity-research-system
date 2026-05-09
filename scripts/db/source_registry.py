from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path

from scripts.db.fact_store import PostgresFactStore


@dataclass(frozen=True)
class SourceVersionInput:
    source_id: str
    source_uri: str
    source_type: str
    checksum: str
    connector_version: str
    raw_path: str | None = None
    effective_date: str | None = None
    published_at: str | None = None
    notes: str | None = None


class SourceRegistry:
    def __init__(self, store: PostgresFactStore | None = None) -> None:
        self.store = store or PostgresFactStore()

    @staticmethod
    def compute_checksum(payload: bytes) -> str:
        return hashlib.sha256(payload).hexdigest()

    @staticmethod
    def compute_version_id(source_id: str, source_uri: str, checksum: str) -> str:
        raw = f"{source_id}|{source_uri}|{checksum}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def get_latest_by_uri(self, source_id: str, source_uri: str) -> tuple[str, str] | None:
        with self.store.conn() as connection:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, checksum
                    FROM source_versions
                    WHERE source_id = %s AND source_uri = %s
                    ORDER BY ingested_at DESC
                    LIMIT 1
                    """,
                    (source_id, source_uri),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return row[0], row[1]

    def register_version(self, data: SourceVersionInput) -> str:
        version_id = self.compute_version_id(data.source_id, data.source_uri, data.checksum)
        with self.store.conn() as connection:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO source_versions
                    (id, source_id, source_uri, source_type, effective_date, published_at,
                     ingested_at, checksum, connector_version, raw_path, notes)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW(), %s, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    (
                        version_id,
                        data.source_id,
                        data.source_uri,
                        data.source_type,
                        data.effective_date,
                        data.published_at,
                        data.checksum,
                        data.connector_version,
                        data.raw_path,
                        data.notes,
                    ),
                )
        return version_id

    def save_raw_snapshot(self, payload: bytes, out_path: Path) -> str:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(payload)
        checksum = self.compute_checksum(payload)
        out_path.with_suffix(out_path.suffix + ".sha256").write_text(checksum, encoding="utf-8")
        return checksum

