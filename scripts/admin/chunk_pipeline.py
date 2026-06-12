from __future__ import annotations

"""Backfill embeddings for ingest.document_chunks in PostgreSQL.

This script is the single embedding pipeline for the repository.
It no longer writes to Milvus; instead it computes embeddings for chunks
already stored in ingest.document_chunks and updates the pgvector column.

Usage:
    python scripts/admin/chunk_pipeline.py
    python scripts/admin/chunk_pipeline.py --ticker DHG
    python scripts/admin/chunk_pipeline.py --batch-size 32 --limit 200
"""

import argparse
import hashlib
import os
from dataclasses import dataclass

from backend.database.vector_store import ChunkEmbeddingRecord, PostgresVectorStore

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional dependency at runtime
    OpenAI = None


DEFAULT_EMBED_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
VECTOR_DIM = 1536


@dataclass(frozen=True)
class PendingChunk:
    chunk_id: int
    source_doc_id: str | None
    ticker: str
    chunk_index: int
    section_title: str
    chunk_text: str
    fiscal_year: int | None
    language: str
    content_hash: str | None
    embedding_model: str | None


def _embed_texts(texts: list[str]) -> list[list[float]]:
    if OpenAI is None or not os.getenv("OPENAI_API_KEY"):
        # Deterministic zero-vector fallback for local dry runs.
        return [[0.0] * VECTOR_DIM for _ in texts]

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.embeddings.create(model=DEFAULT_EMBED_MODEL, input=texts)
    return [item.embedding for item in response.data]


def run_chunk_pipeline(ticker: str | None = None, batch_size: int = 64, limit: int | None = None) -> int:
    store = PostgresVectorStore(vector_dim=VECTOR_DIM)
    rows = store.fetch_chunks_missing_embeddings(ticker=ticker, limit=limit)
    if not rows:
        if ticker:
            print(f"No chunks without embeddings found for ticker {ticker.upper()}")
        else:
            print("No chunks without embeddings found")
        return 0

    total = 0
    for offset in range(0, len(rows), batch_size):
        batch_rows = rows[offset : offset + batch_size]
        texts = [row["chunk_text"] for row in batch_rows]
        embeddings = _embed_texts(texts)

        records = []
        for row, embedding in zip(batch_rows, embeddings, strict=False):
            content_hash = row.get("content_hash") or hashlib.sha256(row["chunk_text"].encode("utf-8")).hexdigest()
            embedding_model = row.get("embedding_model") or DEFAULT_EMBED_MODEL
            records.append(
                ChunkEmbeddingRecord(
                    chunk_id=row["chunk_id"],
                    source_doc_id=row["source_doc_id"],
                    ticker=row["ticker"],
                    chunk_index=row["chunk_index"],
                    section_title=row.get("section_title") or "",
                    chunk_text=row["chunk_text"],
                    fiscal_year=row.get("fiscal_year"),
                    language=row.get("language") or "vi",
                    content_hash=content_hash,
                    embedding_model=embedding_model,
                    embedding=embedding,
                    metadata_json=dict(row.get("metadata_json") or {}),
                )
            )

        updated = store.upsert_embeddings(records)
        total += updated
        print(f"[chunk] updated {updated} embeddings ({min(offset + batch_size, len(rows))}/{len(rows)})")

    print(f"Embedding backfill completed: {total} chunks updated")
    return total


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill pgvector embeddings for document chunks.")
    parser.add_argument("--ticker", type=str, default=None, help="Optional ticker filter.")
    parser.add_argument("--batch-size", type=int, default=64, help="Number of chunks to embed per batch.")
    parser.add_argument("--limit", type=int, default=None, help="Optional cap on chunks to process.")
    parser.add_argument(
        "--root",
        type=str,
        default=None,
        help="Deprecated. Retained for compatibility; ignored because the pipeline now reads from Postgres.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.root:
        print(f"[chunk] --root={args.root} is deprecated and ignored; embeddings are backfilled from Postgres.")
    run_chunk_pipeline(ticker=args.ticker, batch_size=args.batch_size, limit=args.limit)


if __name__ == "__main__":
    main()
