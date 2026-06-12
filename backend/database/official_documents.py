"""Official-document registry — Source-Provenance Rebuild, Phase 1.

Repository methods for the verification layer added in migration 013:

  - ingest.official_documents       (Tier 0/1/2 official documents)
  - fact.fact_observations          (official-source observations)
  - fact.canonical_facts            (verification linkage)
  - fact.verified_financial_facts   (read-only view of final-safe facts)

This sits alongside backend/database/source_registry.py (which owns the *acquisition*
layer, ingest.sources / raw_payloads). Acquisition and verification are kept
separate on purpose — that separation is the whole point of the rebuild.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from backend.database.fact_store import PostgresFactStore

# source_type → default tier for the verification layer (never Tier 3 here).
_OFFICIAL_TYPE_TIER: dict[str, int] = {
    "audited_financial_statement": 0,
    "annual_report": 0,
    "exchange_disclosure": 0,
    "regulatory_notice": 0,
    "official_tender": 0,
    "bhyt_policy": 0,
    "company_ir": 1,
    "news_article": 2,
    "broker_report": 2,
}

# Reconciliation statuses that make a fact safe to cite in a FINAL report.
PROMOTABLE_STATUSES: frozenset[str] = frozenset({"matched_official", "manual_reviewed"})


def tier_for_official_type(source_type: str) -> int:
    return _OFFICIAL_TYPE_TIER.get(source_type, 0)


@dataclass(frozen=True)
class OfficialDocumentInput:
    ticker: str
    source_type: str
    title: str
    company_name: str | None = None
    issuer: str | None = None
    url: str | None = None
    storage_bucket: str | None = None
    storage_path: str | None = None
    content_type: str | None = None
    file_size_bytes: int | None = None
    published_date: str | None = None
    fiscal_year: int | None = None
    language: str = "vi"
    file_hash: str | None = None
    source_tier: int | None = None
    status: str = "registered"
    metadata: dict[str, Any] = field(default_factory=dict)


class OfficialDocumentRegistry:
    def __init__(self, store: PostgresFactStore | None = None) -> None:
        self.store = store or PostgresFactStore()

    @staticmethod
    def compute_file_hash(payload: bytes) -> str:
        return hashlib.sha256(payload).hexdigest()

    def register_official_document(self, data: OfficialDocumentInput) -> str:
        """Register an official document in the canonical source-document table."""
        tier = data.source_tier if data.source_tier is not None else tier_for_official_type(data.source_type)
        from backend.database.canonical.source_dal import upsert_source_document
        return upsert_source_document(
            ticker=data.ticker,
            source_type=data.source_type,
            source_tier=tier,
            source_uri=data.url or (
                f"supabase://{data.storage_bucket}/{data.storage_path}"
                if data.storage_bucket and data.storage_path
                else f"manual:{data.ticker}:{data.title}"
            ),
            checksum=data.file_hash or hashlib.sha256(data.title.encode()).hexdigest(),
            source_title=data.title,
            issuer=data.issuer,
            fiscal_year=data.fiscal_year,
            storage_bucket=data.storage_bucket,
            storage_path=data.storage_path,
            content_type=data.content_type,
            file_size_bytes=data.file_size_bytes,
            language=data.language,
            fetch_status=data.status,
            metadata={"company_name": data.company_name, **data.metadata},
        )

    def get_official_document(self, official_document_id: str) -> dict | None:
        import psycopg2.extras as _extras
        with self.store.conn() as connection:
            with connection.cursor(cursor_factory=_extras.DictCursor) as cur:
                cur.execute(
                    "SELECT * FROM ingest.source_documents WHERE source_doc_id=%s",
                    (official_document_id,),
                )
                row = cur.fetchone()
                return dict(row) if row else None

    def list_official_documents(self, ticker: str) -> list[dict]:
        import psycopg2.extras as _extras
        with self.store.conn() as connection:
            with connection.cursor(cursor_factory=_extras.DictCursor) as cur:
                cur.execute(
                    "SELECT * FROM ingest.source_documents WHERE ticker=%s ORDER BY fiscal_year, source_type",
                    (ticker,),
                )
                return [dict(r) for r in cur.fetchall()]

    def add_official_observation(
        self,
        ticker: str,
        period: str,
        metric: str,
        value: float,
        unit: str,
        official_document_id: str,
        *,
        page_number: int | None = None,
        table_name: str | None = None,
        extracted_text: str | None = None,
        extraction_method: str = "manual",
        confidence: float | None = 1.0,
        currency: str = "VND",
    ) -> int:
        """Insert an official-source observation. Returns observation_id.

        source_tier is taken from the linked official document (0/1/2).
        """
        from backend.database.canonical.observation_dal import insert_observations
        with self.store.conn() as connection:
            with connection.cursor() as cur:
                cur.execute("SELECT source_tier FROM ingest.source_documents WHERE source_doc_id=%s", (official_document_id,))
                row = cur.fetchone()
        if row is None:
            raise ValueError(f"source_doc_id {official_document_id} not found")
        return insert_observations([{
            "ticker": ticker, "period": period, "metric": metric, "value": value,
            "unit": unit, "currency": currency, "source_doc_id": official_document_id,
            "source_tier": row[0], "page_number": page_number, "table_name": table_name,
            "extracted_text": extracted_text, "extraction_method": extraction_method,
            "confidence": confidence,
        }])

    def mark_fact_verified(
        self,
        fact_id: str,
        official_document_id: str,
        reconciliation_status: str = "matched_official",
        verified_by: str = "reconciler",
    ) -> None:
        """Link a canonical fact to its official document and set verification status.

        The DB CHECK chk_verified_requires_official_doc guarantees a fact cannot be
        marked matched_official / manual_reviewed without an official_document_id.
        """
        if reconciliation_status not in {
            "matched_official", "mismatch", "missing_official",
            "missing_api", "manual_review_required", "manual_reviewed",
        }:
            raise ValueError(f"invalid reconciliation_status: {reconciliation_status}")
        with self.store.conn() as connection:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    UPDATE fact.canonical_facts
                    SET official_document_id  = %s,
                        reconciliation_status = %s,
                        verified_by           = %s,
                        verified_at           = NOW(),
                        updated_at            = NOW()
                    WHERE fact_id = %s
                    """,
                    (official_document_id, reconciliation_status, verified_by, fact_id),
                )

    def insert_official_canonical_fact(
        self,
        ticker: str,
        period: str,
        metric: str,
        value: float,
        official_document_id: str,
        unit: str = "vnd_bn",
        currency: str = "V",
        source_tier: int = 0,
        verified_by: str = "official_doc_only",
    ) -> str:
        """Insert a canonical fact sourced entirely from an official document.

        Used for official-only years where no API/Tier-3 counterpart exists.
        The fact is immediately marked manual_reviewed and linked to the document.
        Returns the generated fact_id.
        """
        import hashlib
        fact_id = hashlib.sha256(
            f"{ticker}_{period}_{metric}_official_{official_document_id}".encode()
        ).hexdigest()[:32]
        period_type = period[4:] if len(period) > 4 else "FY"

        with self.store.conn() as connection:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO fact.canonical_facts
                    (fact_id, ticker, period, period_type, canonical_version, metric,
                     value, unit, currency, selected_observation_id, selection_policy,
                     confidence, quality_status, source_tier, official_document_id,
                     reconciliation_status, verified_by, verified_at)
                    VALUES (%s, %s, %s, %s, %s, %s,
                            %s, %s, %s, NULL, %s,
                            %s, %s, %s, %s,
                            %s, %s, NOW())
                    ON CONFLICT (fact_id) DO UPDATE SET
                        official_document_id  = EXCLUDED.official_document_id,
                        reconciliation_status = EXCLUDED.reconciliation_status,
                        verified_by           = EXCLUDED.verified_by,
                        verified_at           = NOW(),
                        updated_at            = NOW()
                    """,
                    (
                        fact_id, ticker, period, period_type, "v_official", metric,
                        value, unit, currency, "official_doc_only",
                        0.95, "accepted", source_tier, official_document_id,
                        "manual_reviewed", verified_by,
                    ),
                )
        return fact_id

    def get_verified_facts(self, ticker: str, canonical_version: str | None = None) -> list[dict]:
        """Return final-report-safe canonical facts."""
        import psycopg2.extras as _extras
        with self.store.conn() as connection:
            with connection.cursor(cursor_factory=_extras.DictCursor) as cur:
                if canonical_version:
                    cur.execute(
                        "SELECT * FROM fact.canonical_facts "
                        "WHERE ticker=%s AND canonical_version=%s "
                        "AND reconciliation_status IN ('matched_official','manual_reviewed') ORDER BY period, metric",
                        (ticker, canonical_version),
                    )
                else:
                    cur.execute(
                        "SELECT * FROM fact.canonical_facts WHERE ticker=%s "
                        "AND reconciliation_status IN ('matched_official','manual_reviewed') ORDER BY period, metric",
                        (ticker,),
                    )
                return [dict(r) for r in cur.fetchall()]
