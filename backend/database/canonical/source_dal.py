"""v2 DAL: ingest.source_documents â€” source document registry.

Write permission: connector modules, ingest_official_documents.py.
Read permission: all modules.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, UTC
from typing import Any

from backend.database.canonical.connection import get_conn


def compute_source_doc_id(source_type: str, source_uri: str, checksum: str) -> str:
    """Compute deterministic source_doc_id = SHA256(source_type || source_uri || checksum)."""
    raw = f"{source_type}|{source_uri}|{checksum}"
    return hashlib.sha256(raw.encode()).hexdigest()


def upsert_source_document(
    ticker: str | None,
    source_type: str,
    source_tier: int,
    source_uri: str,
    checksum: str,
    source_title: str | None = None,
    issuer: str | None = None,
    published_at: datetime | None = None,
    fiscal_year: int | None = None,
    fiscal_period: str | None = None,
    storage_bucket: str | None = None,
    storage_path: str | None = None,
    content_type: str | None = None,
    file_size_bytes: int | None = None,
    uploaded_at: datetime | None = None,
    language: str = "vi",
    fetch_status: str = "registered",
    connector_name: str | None = None,
    connector_version: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    """Insert or update a source document. Returns source_doc_id.

    The deterministic primary key deduplicates repeated registrations and lets
    later calls enrich storage metadata without creating a second source row.
    """
    source_doc_id = compute_source_doc_id(source_type, source_uri, checksum)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ingest.source_documents (
                    source_doc_id, ticker, source_type, source_tier,
                    source_uri, source_title, issuer, published_at,
                    fiscal_year, fiscal_period, checksum, storage_bucket, storage_path,
                    content_type, file_size_bytes, uploaded_at, language,
                    fetch_status, connector_name, connector_version, metadata_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (source_doc_id) DO UPDATE
                SET source_title      = COALESCE(EXCLUDED.source_title, ingest.source_documents.source_title),
                    storage_bucket    = COALESCE(EXCLUDED.storage_bucket, ingest.source_documents.storage_bucket),
                    storage_path      = COALESCE(EXCLUDED.storage_path, ingest.source_documents.storage_path),
                    content_type      = COALESCE(EXCLUDED.content_type, ingest.source_documents.content_type),
                    file_size_bytes   = COALESCE(EXCLUDED.file_size_bytes, ingest.source_documents.file_size_bytes),
                    uploaded_at       = COALESCE(EXCLUDED.uploaded_at, ingest.source_documents.uploaded_at),
                    fetch_status      = EXCLUDED.fetch_status,
                    connector_name    = COALESCE(EXCLUDED.connector_name, ingest.source_documents.connector_name),
                    connector_version = COALESCE(EXCLUDED.connector_version, ingest.source_documents.connector_version),
                    metadata_json     = COALESCE(ingest.source_documents.metadata_json, '{}'::jsonb)
                                        || COALESCE(EXCLUDED.metadata_json, '{}'::jsonb)
                """,
                (
                    source_doc_id,
                    ticker,
                    source_type,
                    source_tier,
                    source_uri,
                    source_title,
                    issuer,
                    published_at,
                    fiscal_year,
                    fiscal_period,
                    checksum,
                    storage_bucket,
                    storage_path,
                    content_type,
                    file_size_bytes,
                    uploaded_at,
                    language,
                    fetch_status,
                    connector_name,
                    connector_version,
                    json.dumps(metadata or {}),
                ),
            )
    return source_doc_id


def get_source_documents_for_ticker(
    ticker: str,
    source_type: str | None = None,
    min_tier: int = 0,
    max_tier: int = 3,
) -> list[dict[str, Any]]:
    """Return source documents for a ticker, optionally filtered by type and tier."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            query = """
                SELECT source_doc_id, ticker, source_type, source_tier,
                       source_uri, source_title, issuer, published_at,
                       fiscal_year, fiscal_period, fetch_status,
                       connector_name, metadata_json, created_at
                FROM ingest.source_documents
                WHERE ticker = %s
                  AND source_tier BETWEEN %s AND %s
            """
            params: list[Any] = [ticker, min_tier, max_tier]
            if source_type:
                query += " AND source_type = %s"
                params.append(source_type)
            query += " ORDER BY created_at DESC"
            cur.execute(query, params)
            cols = [d.name for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]


def update_fetch_status(source_doc_id: str, status: str) -> None:
    """Update fetch_status for a source document."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE ingest.source_documents SET fetch_status = %s WHERE source_doc_id = %s",
                (status, source_doc_id),
            )

