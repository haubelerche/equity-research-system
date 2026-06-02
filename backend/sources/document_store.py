"""Fetched-document storage — Source-Provenance Rebuild, Phase 5.

Stores fetched source documents on disk under data/source_documents/<source_name>/ and
returns a FetchedDocument with raw_content_hash. Optionally persists a row to
ingest.official_documents (Tier 0-2 catalyst sources are part of the verification layer)
so catalyst_events can FK to a concrete source_document_id.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

_STORE_ROOT = Path(__file__).resolve().parents[2] / "data" / "source_documents"


@dataclass
class FetchedDocument:
    source_name: str
    source_type: str
    source_tier: int
    url: str
    title: str
    raw_content: bytes
    raw_content_hash: str
    local_path: str
    publisher: str | None = None
    published_date: str | None = None
    language: str = "vi"
    fetched_at: str = ""

    def to_dict(self) -> dict:
        return {
            "source_name": self.source_name, "source_type": self.source_type,
            "source_tier": self.source_tier, "url": self.url, "title": self.title,
            "raw_content_hash": self.raw_content_hash, "local_path": self.local_path,
            "publisher": self.publisher, "published_date": self.published_date,
            "language": self.language, "fetched_at": self.fetched_at,
        }


def compute_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def store_document(
    *,
    source_name: str,
    source_type: str,
    source_tier: int,
    url: str,
    title: str,
    content: bytes,
    publisher: str | None = None,
    published_date: str | None = None,
    language: str = "vi",
    store_root: Path | None = None,
) -> FetchedDocument:
    """Persist raw content to disk and return a FetchedDocument with its content hash."""
    root = store_root or _STORE_ROOT
    content_hash = compute_hash(content)
    dest_dir = root / source_name
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{content_hash[:16]}.bin"
    dest.write_bytes(content)
    dest.with_suffix(".sha256").write_text(content_hash, encoding="utf-8")
    return FetchedDocument(
        source_name=source_name, source_type=source_type, source_tier=source_tier,
        url=url, title=title, raw_content=content, raw_content_hash=content_hash,
        local_path=str(dest), publisher=publisher, published_date=published_date,
        language=language, fetched_at=datetime.now(UTC).isoformat(),
    )


# Map catalyst source_type → official_documents.source_type (verification layer).
_SOURCE_TYPE_TO_OFFICIAL = {
    "exchange_disclosure": "exchange_disclosure",
    "company_ir": "company_ir",
    "regulatory_notice": "regulatory_notice",
    "official_tender": "official_tender",
    "bhyt_policy": "bhyt_policy",
    "financial_media": "news_article",
    "broker_report": "broker_report",
}


def persist_to_official_documents(doc: FetchedDocument, ticker: str | None, registry=None) -> int:
    """Persist a fetched catalyst document into ingest.official_documents. Returns its id."""
    from backend.database.official_documents import (
        OfficialDocumentInput,
        OfficialDocumentRegistry,
    )
    reg = registry or OfficialDocumentRegistry()
    return reg.register_official_document(OfficialDocumentInput(
        ticker=ticker,
        source_type=_SOURCE_TYPE_TO_OFFICIAL.get(doc.source_type, "regulatory_notice"),
        title=doc.title,
        issuer=doc.publisher,
        url=doc.url,
        local_path=doc.local_path,
        published_date=doc.published_date,
        language=doc.language,
        file_hash=doc.raw_content_hash,
        source_tier=doc.source_tier,
        status="fetched",
    ))
