"""Evidence retrieval service — Phase 5 citation pipeline.

Queries ingest.document_chunks with full-text search, metadata filters,
and source-tier prioritisation. Used by report generation and citation
validation; replaces the legacy file-based keyword stub.

Retrieval priority:
  Tier 1 (reliability_tier=1) — official PDFs (text or OCR) > Tier 2 > Tier 3
  Within same tier: FTS rank descending.

Interface:
    svc = RetrievalService()
    chunks = svc.retrieve(ticker="DHG", query="doanh thu", fiscal_year=2023, top_k=5)
    for c in chunks:
        print(c.source_id, c.page_number, c.extraction_method)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_PROJECT_ROOT = str(Path(__file__).resolve().parents[1])

_env_file = Path(_PROJECT_ROOT) / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))


def _dsn() -> str:
    return os.getenv("DATABASE_URL", "postgresql://maer:maer_local@localhost:5432/maer_dev")


@dataclass
class EvidenceChunk:
    """A retrieved document chunk with full citation provenance."""
    chunk_id: int
    source_id: str
    ticker: str
    chunk_index: int
    section_title: str
    chunk_text: str
    fiscal_year: int | None
    reliability_tier: int          # 1=official, 2=market, 3=api (lower is better)
    extraction_method: str         # "pdf_text" | "ocr" | "synthetic_facts" | "document" | "cafef_api"
    page_number: int | None        # None for non-page sources (synthetic, API)
    document_id: str | None        # OCR/PDF document identity
    source_title: str
    source_uri: str
    metadata: dict = field(default_factory=dict)

    @property
    def citation_key(self) -> str:
        """Stable key for citation maps: source_id/chunk_index."""
        return f"{self.source_id}/{self.chunk_index}"

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "source_id": self.source_id,
            "ticker": self.ticker,
            "chunk_index": self.chunk_index,
            "section_title": self.section_title,
            "text": self.chunk_text,
            "fiscal_year": self.fiscal_year,
            "reliability_tier": self.reliability_tier,
            "extraction_method": self.extraction_method,
            "page_number": self.page_number,
            "document_id": self.document_id,
            "source_title": self.source_title,
            "source_uri": self.source_uri,
            "citation_key": self.citation_key,
        }


class RetrievalService:
    """DB-backed evidence retrieval with FTS, metadata filtering, and tier prioritisation."""

    def retrieve(
        self,
        ticker: str,
        query: str,
        fiscal_year: int | None = None,
        top_k: int = 5,
        max_tier: int = 3,
        extraction_methods: list[str] | None = None,
    ) -> list[EvidenceChunk]:
        """Retrieve evidence chunks for a query.

        Args:
            ticker: Stock ticker (e.g. "DHG").
            query: Natural-language query (e.g. "doanh thu thuần 2023").
            fiscal_year: If set, filters to chunks for that specific year plus
                         chunks with fiscal_year IS NULL (always-relevant sources).
            top_k: Maximum chunks to return.
            max_tier: Exclude sources with reliability_tier > max_tier.
            extraction_methods: If set, restrict to these methods
                (e.g. ["ocr", "pdf_text"] to exclude synthetic facts).

        Returns:
            List of EvidenceChunk ordered by (reliability_tier ASC, fts_rank DESC).
        """
        try:
            import psycopg2
            import psycopg2.extras
        except ImportError:
            return []

        ticker = ticker.strip().upper()

        try:
            conn = psycopg2.connect(_dsn())
        except Exception:
            return []

        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                params: list[Any] = [ticker, max_tier]

                # Build FTS condition — gracefully degrade to ILIKE if query is empty
                if query and query.strip():
                    # Use simple dictionary for cross-language Vietnamese + number support
                    fts_clause = (
                        "AND to_tsvector('simple', dc.chunk_text) "
                        "@@ plainto_tsquery('simple', %s)"
                    )
                    rank_expr = (
                        "ts_rank(to_tsvector('simple', dc.chunk_text), "
                        "plainto_tsquery('simple', %s))"
                    )
                    params.extend([query, query])
                else:
                    fts_clause = ""
                    rank_expr = "0.0"

                # Fiscal year filter
                if fiscal_year is not None:
                    fy_clause = "AND (dc.fiscal_year = %s OR dc.fiscal_year IS NULL)"
                    params.append(fiscal_year)
                else:
                    fy_clause = ""

                # Extraction method filter
                if extraction_methods:
                    method_placeholders = ",".join(["%s"] * len(extraction_methods))
                    method_clause = (
                        f"AND (dc.metadata_json->>'extraction_method' IN ({method_placeholders})"
                        f" OR dc.metadata_json->>'extraction_method' IS NULL)"
                    )
                    params.extend(extraction_methods)
                else:
                    method_clause = ""

                params.append(top_k)

                sql = f"""
                    SELECT
                        dc.chunk_id,
                        dc.source_id,
                        dc.ticker,
                        dc.chunk_index,
                        dc.section_title,
                        dc.chunk_text,
                        dc.fiscal_year,
                        dc.metadata_json,
                        s.reliability_tier,
                        COALESCE(s.source_title, '') AS source_title,
                        COALESCE(s.source_uri, '') AS source_uri,
                        {rank_expr} AS fts_rank
                    FROM ingest.document_chunks dc
                    JOIN ingest.sources s ON s.source_id = dc.source_id
                    WHERE dc.ticker = %s
                      AND s.reliability_tier <= %s
                      {fts_clause}
                      {fy_clause}
                      {method_clause}
                    ORDER BY s.reliability_tier ASC, fts_rank DESC
                    LIMIT %s
                """

                cur.execute(sql, params)
                rows = cur.fetchall()

        except Exception:
            conn.close()
            return []
        finally:
            conn.close()

        chunks = []
        for row in rows:
            meta = dict(row.get("metadata_json") or {})
            chunks.append(EvidenceChunk(
                chunk_id=row["chunk_id"],
                source_id=row["source_id"],
                ticker=row["ticker"],
                chunk_index=row["chunk_index"],
                section_title=row.get("section_title") or "",
                chunk_text=row["chunk_text"],
                fiscal_year=row.get("fiscal_year"),
                reliability_tier=row.get("reliability_tier", 3),
                extraction_method=meta.get("extraction_method", "unknown"),
                page_number=meta.get("page_number"),
                document_id=meta.get("document_id"),
                source_title=row.get("source_title", ""),
                source_uri=row.get("source_uri", ""),
                metadata=meta,
            ))

        return chunks

    def retrieve_for_metric(
        self,
        ticker: str,
        metric_id: str,
        fiscal_year: int | None = None,
        top_k: int = 3,
    ) -> list[EvidenceChunk]:
        """Retrieve evidence for a specific financial metric ID.

        Searches chunk text for the metric label and the metric_id string.
        Prioritises official sources (tier 1).
        """
        query = metric_id.replace(".", " ").replace("_", " ")
        return self.retrieve(
            ticker=ticker,
            query=query,
            fiscal_year=fiscal_year,
            top_k=top_k,
            max_tier=3,
        )

    def evidence_for_claims(
        self,
        ticker: str,
        claims: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Backward-compatible interface for report generation.

        Each claim dict should have: claim_id, metric_key, fiscal_year (optional).
        Returns list of dicts with claim_id and evidence chunks.
        """
        results: list[dict[str, Any]] = []
        for claim in claims:
            claim_id = claim.get("claim_id", "")
            metric_key = str(claim.get("metric_key", ""))
            fy = claim.get("fiscal_year")

            query = metric_key.replace(".", " ").replace("_", " ")
            chunks = self.retrieve(
                ticker=ticker,
                query=query,
                fiscal_year=fy,
                top_k=3,
            )

            results.append({
                "claim_id": claim_id,
                "chunks": [c.to_dict() for c in chunks],
                "supported": len(chunks) > 0,
                "best_source_tier": chunks[0].reliability_tier if chunks else None,
            })

        return results

    def get_chunk_by_id(self, chunk_id: int) -> EvidenceChunk | None:
        """Fetch a specific chunk by its primary key for citation validation."""
        try:
            import psycopg2
            import psycopg2.extras
            conn = psycopg2.connect(_dsn())
        except Exception:
            return None

        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT dc.*, s.reliability_tier,
                           COALESCE(s.source_title, '') AS source_title,
                           COALESCE(s.source_uri, '') AS source_uri
                    FROM ingest.document_chunks dc
                    JOIN ingest.sources s ON s.source_id = dc.source_id
                    WHERE dc.chunk_id = %s
                    """,
                    (chunk_id,),
                )
                row = cur.fetchone()
        finally:
            conn.close()

        if not row:
            return None

        meta = dict(row.get("metadata_json") or {})
        return EvidenceChunk(
            chunk_id=row["chunk_id"],
            source_id=row["source_id"],
            ticker=row["ticker"],
            chunk_index=row["chunk_index"],
            section_title=row.get("section_title") or "",
            chunk_text=row["chunk_text"],
            fiscal_year=row.get("fiscal_year"),
            reliability_tier=row.get("reliability_tier", 3),
            extraction_method=meta.get("extraction_method", "unknown"),
            page_number=meta.get("page_number"),
            document_id=meta.get("document_id"),
            source_title=row.get("source_title", ""),
            source_uri=row.get("source_uri", ""),
            metadata=meta,
        )

    def source_exists(self, source_id: str) -> bool:
        """Check whether a source_id is present in ingest.sources."""
        try:
            import psycopg2
            conn = psycopg2.connect(_dsn())
        except Exception:
            return False

        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM ingest.sources WHERE source_id = %s LIMIT 1",
                    (source_id,),
                )
                return cur.fetchone() is not None
        finally:
            conn.close()
