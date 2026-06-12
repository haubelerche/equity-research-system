"""Fetched non-official source storage using the private archive bucket."""
from __future__ import annotations

import hashlib
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime

from backend.storage import ARCHIVE_BUCKET, SupabaseStorageAdapter, archive_key


@dataclass
class FetchedDocument:
    source_name: str
    source_type: str
    source_tier: int
    url: str
    title: str
    raw_content: bytes
    raw_content_hash: str
    storage_bucket: str
    storage_path: str
    publisher: str | None = None
    published_date: str | None = None
    language: str = "vi"
    fetched_at: str = ""

    def to_dict(self) -> dict:
        return {
            "source_name": self.source_name, "source_type": self.source_type,
            "source_tier": self.source_tier, "url": self.url, "title": self.title,
            "raw_content_hash": self.raw_content_hash, "storage_bucket": self.storage_bucket,
            "storage_path": self.storage_path, "publisher": self.publisher,
            "published_date": self.published_date, "language": self.language,
            "fetched_at": self.fetched_at,
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
    storage_adapter=None,
    store_root=None,
) -> FetchedDocument:
    content_hash = compute_hash(content)
    key = archive_key("legacy", f"{content_hash}/{source_name}.bin")
    adapter = storage_adapter or SupabaseStorageAdapter()
    with tempfile.NamedTemporaryFile(suffix=".bin") as temporary:
        temporary.write(content)
        temporary.flush()
        if adapter.exists(ARCHIVE_BUCKET, key):
            if not adapter.validate_checksum(ARCHIVE_BUCKET, key, content_hash):
                raise FileExistsError(f"Checksum conflict: {ARCHIVE_BUCKET}/{key}")
        else:
            adapter.upload_file(ARCHIVE_BUCKET, key, temporary.name, "application/octet-stream")
    return FetchedDocument(
        source_name=source_name, source_type=source_type, source_tier=source_tier,
        url=url, title=title, raw_content=content, raw_content_hash=content_hash,
        storage_bucket=ARCHIVE_BUCKET, storage_path=key, publisher=publisher,
        published_date=published_date, language=language, fetched_at=datetime.now(UTC).isoformat(),
    )


def persist_to_official_documents(doc: FetchedDocument, ticker: str | None, registry=None) -> str:
    from backend.database.official_documents import OfficialDocumentInput, OfficialDocumentRegistry

    reg = registry or OfficialDocumentRegistry()
    return reg.register_official_document(OfficialDocumentInput(
        ticker=ticker,
        source_type="regulatory_notice",
        title=doc.title,
        issuer=doc.publisher,
        url=doc.url,
        storage_bucket=doc.storage_bucket,
        storage_path=doc.storage_path,
        content_type="application/octet-stream",
        file_size_bytes=len(doc.raw_content),
        published_date=doc.published_date,
        language=doc.language,
        file_hash=doc.raw_content_hash,
        source_tier=doc.source_tier,
        status="fetched",
    ))
