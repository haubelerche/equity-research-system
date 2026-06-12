from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Iterable

import psycopg2
import psycopg2.extras

from backend.database.canonical.connection import get_conn
from backend.database.config import require_database_url


DEFAULT_VECTOR_DIM = 1536


@dataclass(frozen=True)
class ChunkEmbeddingRecord:
    chunk_id: int
    source_doc_id: str | None
    ticker: str
    chunk_index: int
    section_title: str
    chunk_text: str
    fiscal_year: int | None
    language: str
    content_hash: str
    embedding_model: str
    embedding: list[float]
    metadata_json: dict[str, Any] = field(default_factory=dict)


class PostgresVectorStore:
    """Vector-enabled document chunk storage on PostgreSQL/pgvector."""

    def __init__(self, dsn: str | None = None, vector_dim: int = DEFAULT_VECTOR_DIM) -> None:
        self.dsn = require_database_url(dsn)
        self.vector_dim = vector_dim

    @staticmethod
    def _vector_literal(values: list[float]) -> str:
        return "[" + ",".join(repr(float(v)) for v in values) + "]"

    def fetch_chunks_missing_embeddings(
        self,
        ticker: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        params: list[Any] = []
        where = ["dc.embedding IS NULL"]
        if ticker:
            where.append("dc.ticker = %s")
            params.append(ticker.strip().upper())

        sql = f"""
            SELECT
                dc.chunk_id,
                dc.source_doc_id,
                dc.ticker,
                dc.chunk_index,
                dc.section_title,
                dc.chunk_text,
                dc.fiscal_year,
                dc.language,
                dc.content_hash,
                dc.embedding_model,
                dc.metadata_json
            FROM ingest.document_chunks dc
            WHERE {' AND '.join(where)}
            ORDER BY dc.created_at ASC, dc.chunk_id ASC
        """
        if limit is not None:
            sql += " LIMIT %s"
            params.append(limit)

        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                return [dict(row) for row in cur.fetchall()]

    def upsert_embeddings(self, records: Iterable[ChunkEmbeddingRecord]) -> int:
        payload = []
        for record in records:
            payload.append(
                (
                    self._vector_literal(record.embedding),
                    record.embedding_model,
                    record.content_hash,
                    record.chunk_id,
                )
            )

        if not payload:
            return 0

        with get_conn() as conn:
            with conn.cursor() as cur:
                psycopg2.extras.execute_batch(
                    cur,
                    """
                    UPDATE ingest.document_chunks
                    SET embedding = %s::vector,
                        embedding_model = %s,
                        content_hash = %s
                    WHERE chunk_id = %s
                    """,
                    payload,
                    page_size=100,
                )
        return len(payload)

    def search(
        self,
        embedding: list[float],
        top_k: int = 8,
        ticker: str | None = None,
        max_tier: int = 3,
        output_fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        fields = output_fields or [
            "chunk_id",
            "source_doc_id",
            "ticker",
            "chunk_index",
            "section_title",
            "chunk_text",
            "fiscal_year",
            "language",
            "content_hash",
            "embedding_model",
            "metadata_json",
            "source_tier",
            "source_title",
            "source_uri",
        ]
        select_fields = ", ".join([f"dc.{field}" if field not in {"source_tier", "source_title", "source_uri"} else f"s.{field}" for field in fields])
        vector_literal = self._vector_literal(embedding)

        params: list[Any] = [vector_literal]
        where = ["dc.embedding IS NOT NULL", "s.source_tier <= %s"]
        params.append(max_tier)
        if ticker:
            where.append("dc.ticker = %s")
            params.append(ticker.strip().upper())

        sql = f"""
            SELECT
                {select_fields},
                (1 - (dc.embedding <=> %s::vector)) AS similarity_score
            FROM ingest.document_chunks dc
            JOIN ingest.source_documents s ON s.source_doc_id = dc.source_doc_id
            WHERE {' AND '.join(where)}
            ORDER BY s.source_tier ASC, dc.embedding <=> %s::vector ASC
            LIMIT %s
        """
        params.extend([vector_literal, top_k])

        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                return [dict(row) for row in cur.fetchall()]
