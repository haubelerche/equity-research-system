"""Evidence retrieval service — evidence pipeline for document chunks.

Queries ingest.document_chunks with vector similarity when embeddings are
available, and falls back to full-text search when embeddings or an
embedding provider are unavailable. Metadata filters and source-tier
prioritisation remain in PostgreSQL.

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

from backend.database.config import connect_with_retry, require_database_url

_PROJECT_ROOT = str(Path(__file__).resolve().parents[1])

_env_file = Path(_PROJECT_ROOT) / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))


def _dsn() -> str:
    return require_database_url()


DEFAULT_EMBED_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
VECTOR_DIM = 1536

# Per-tier cosine-distance penalty applied on the vector retrieval path so that
# official (tier-1) sources are preferred at near-equal similarity, while a
# clearly-more-relevant lower-tier chunk (e.g. a reconciled canonical fact that
# holds the exact figure a narrative annual-report page lacks) can still surface
# into top-k. With cosine distance in [0, ~1], 0.03 means a tier-3 chunk must be
# ~0.06 closer than a tier-1 chunk to outrank it.
TIER_RANK_PENALTY = float(os.getenv("RETRIEVAL_TIER_RANK_PENALTY", "0.20"))

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional dependency at runtime
    OpenAI = None


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(repr(float(v)) for v in values) + "]"


def _embed_query(query: str) -> list[float] | None:
    if OpenAI is None or not os.getenv("OPENAI_API_KEY"):
        return None
    if not query.strip():
        return None
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.embeddings.create(model=DEFAULT_EMBED_MODEL, input=[query])
    return response.data[0].embedding


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

        import os as _os
        from backend.retrieval_enhance import expand_query as _expand_query
        _variants = _expand_query(query) if _os.getenv("RAG_QUERY_EXPANSION") == "1" else [query]
        _rerank = _os.getenv("RAG_RERANK") == "1"
        _pool_size = max(20, top_k) if _rerank else top_k

        ticker = ticker.strip().upper()
        query_embedding = _embed_query(query)

        try:
            conn = connect_with_retry(_dsn())
        except Exception:
            return []

        try:
            def _run_search(use_vector: bool, _q: str = query, _qe: list[float] | None = query_embedding) -> list[dict[str, Any]]:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    # Params MUST be appended in the same left-to-right order the %s
                    # placeholders appear in the final SQL: rank_expr (SELECT), then the
                    # WHERE clauses (ticker, tier, fts, fiscal year, methods), then
                    # order_expr (ORDER BY), then LIMIT. Getting this order wrong silently
                    # binds e.g. the ticker to the ::vector cast and the whole query fails.
                    rank_param: Any = None
                    fts_where_param: Any = None
                    order_param: Any = None
                    # Strict tier-first ordering is correct for the lexical/FTS path,
                    # but on the vector path it exiles the canonical-fact (tier-3)
                    # evidence beneath dozens of tier-1 narrative chunks that never
                    # actually contain the requested figure. The vector path instead
                    # blends similarity with a small per-tier distance penalty
                    # (TIER_RANK_PENALTY): official (tier-1) sources still win on
                    # near-equal similarity, but a clearly-more-relevant lower-tier
                    # chunk can surface. So we drop the tier-first prefix there.
                    tier_order = "s.source_tier ASC, "

                    if use_vector and _qe is not None:
                        vector_param = _vector_literal(_qe)
                        rank_expr = "(1 - (dc.embedding <=> %s::vector))"
                        order_expr = (
                            f"((dc.embedding <=> %s::vector) "
                            f"+ {TIER_RANK_PENALTY} * GREATEST(s.source_tier - 1, 0)) ASC"
                        )
                        extra_where = "AND dc.embedding IS NOT NULL"
                        fts_clause = ""
                        rank_param = vector_param
                        order_param = vector_param
                        tier_order = ""
                    elif _q and _q.strip():
                        # Use simple dictionary for cross-language Vietnamese + number support.
                        fts_clause = (
                            "AND to_tsvector('simple', dc.chunk_text) "
                            "@@ plainto_tsquery('simple', %s)"
                        )
                        rank_expr = (
                            "ts_rank(to_tsvector('simple', dc.chunk_text), "
                            "plainto_tsquery('simple', %s))"
                        )
                        order_expr = "fts_rank DESC"
                        extra_where = ""
                        rank_param = _q
                        fts_where_param = _q
                    else:
                        rank_expr = "0.0"
                        order_expr = "fts_rank DESC"
                        extra_where = ""
                        fts_clause = ""

                    fy_clause = (
                        "AND (dc.fiscal_year = %s OR dc.fiscal_year IS NULL)"
                        if fiscal_year is not None else ""
                    )
                    if extraction_methods:
                        method_placeholders = ",".join(["%s"] * len(extraction_methods))
                        method_clause = (
                            f"AND (dc.metadata_json->>'extraction_method' IN ({method_placeholders})"
                            f" OR dc.metadata_json->>'extraction_method' IS NULL)"
                        )
                    else:
                        method_clause = ""

                    # Assemble params in SQL placeholder order.
                    params: list[Any] = []
                    if rank_param is not None:
                        params.append(rank_param)          # {rank_expr} in SELECT
                    params.append(ticker)                  # WHERE dc.ticker = %s
                    params.append(max_tier)                # AND s.source_tier <= %s
                    if fts_where_param is not None:
                        params.append(fts_where_param)     # {fts_clause}
                    if fiscal_year is not None:
                        params.append(fiscal_year)         # {fy_clause}
                    if extraction_methods:
                        params.extend(extraction_methods)  # {method_clause}
                    if order_param is not None:
                        params.append(order_param)         # {order_expr} in ORDER BY
                    params.append(_pool_size)               # LIMIT %s

                    sql = f"""
                        SELECT
                            dc.chunk_id,
                            dc.source_doc_id AS source_id,
                            dc.ticker,
                            dc.chunk_index,
                            dc.section_title,
                            dc.chunk_text,
                            dc.fiscal_year,
                            dc.metadata_json,
                            s.source_tier AS reliability_tier,
                            COALESCE(s.source_title, '') AS source_title,
                            COALESCE(s.source_uri, '') AS source_uri,
                            {rank_expr} AS fts_rank
                        FROM ingest.document_chunks dc
                        JOIN ingest.source_documents s ON s.source_doc_id = dc.source_doc_id
                        WHERE dc.ticker = %s
                          AND s.source_tier <= %s
                          {extra_where}
                          {fts_clause}
                          {fy_clause}
                          {method_clause}
                        ORDER BY {tier_order}{order_expr}
                        LIMIT %s
                    """

                    cur.execute(sql, params)
                    return cur.fetchall()

            # Run search for each query variant; merge results deduped by chunk_id.
            import os as _os2
            from backend.retrieval_enhance import reciprocal_rank_fusion as _rrf
            _hybrid = _os2.getenv("RAG_HYBRID_FUSION") == "1"

            all_rows: list[dict[str, Any]] = []
            seen_ids: set[int] = set()
            for _variant in _variants:
                _variant_embedding = _embed_query(_variant) if _variant != query else query_embedding
                if _hybrid:
                    # Run BOTH vector and FTS paths, fuse with RRF.
                    _candidate_lists: list[list[dict[str, Any]]] = []
                    if _variant_embedding is not None:
                        _vector_rows = _run_search(True, _variant, _variant_embedding)
                        if _vector_rows:
                            _candidate_lists.append(_vector_rows)
                    _fts_rows = _run_search(False, _variant, None)
                    if _fts_rows:
                        _candidate_lists.append(_fts_rows)
                    _variant_rows = _rrf(_candidate_lists, key="chunk_id") if _candidate_lists else []
                else:
                    # Original single-path behaviour: vector when embedding available, else FTS.
                    _variant_rows = _run_search(_variant_embedding is not None, _variant, _variant_embedding)
                    if not _variant_rows and _variant and _variant.strip() and _variant_embedding is not None:
                        _variant_rows = _run_search(False, _variant, None)
                for _r in _variant_rows:
                    _cid = _r["chunk_id"]
                    if _cid not in seen_ids:
                        seen_ids.add(_cid)
                        all_rows.append(_r)
            if _rerank and all_rows:
                from backend.retrieval_enhance import llm_rerank as _llm_rerank
                all_rows = _llm_rerank(query, all_rows, top_k=top_k)
            rows = all_rows[:top_k]

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
            conn = connect_with_retry(_dsn())
        except Exception:
            return None

        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT dc.chunk_id, dc.source_doc_id AS source_id, dc.ticker,
                           dc.chunk_index, dc.section_title, dc.chunk_text,
                           dc.fiscal_year, dc.metadata_json,
                           s.source_tier AS reliability_tier,
                           COALESCE(s.source_title, '') AS source_title,
                           COALESCE(s.source_uri, '') AS source_uri
                    FROM ingest.document_chunks dc
                    JOIN ingest.source_documents s ON s.source_doc_id = dc.source_doc_id
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
        """Check whether a source_doc_id is present in ingest.source_documents."""
        try:
            import psycopg2
            conn = connect_with_retry(_dsn())
        except Exception:
            return False

        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM ingest.source_documents WHERE source_doc_id = %s LIMIT 1",
                    (source_id,),
                )
                return cur.fetchone() is not None
        finally:
            conn.close()
