"""Official document discovery orchestrator — Source-Provenance Rebuild, Phase 3A/3B.

Phase 3A (Discovery): run the controlled connectors → candidates → rank.
Phase 3B (Fetching): download approved candidates, store raw file + sha256 hash.

Discovery and fetch are SEPARATE steps (a candidate is just metadata; only an approved,
sufficiently-confident candidate is fetched). Fetching uses TLS-verified HTTP.
"""
from __future__ import annotations

import hashlib
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from backend.documents.company_registry import get_company
from backend.documents.connectors.base import DocumentCandidate
from backend.documents.connectors.company_ir_connector import CompanyIRConnector
from backend.documents.connectors.hnx_disclosure_connector import HnxDisclosureConnector
from backend.documents.connectors.hose_disclosure_connector import HoseDisclosureConnector
from backend.documents.connectors.ssc_disclosure_connector import SscDisclosureConnector
from backend.documents.document_candidate_ranker import (
    DEFAULT_MIN_CONFIDENCE,
    RankingResult,
    rank_candidates,
)

# Default connector set, in priority order.
DEFAULT_CONNECTORS = [
    CompanyIRConnector(),
    HoseDisclosureConnector(),
    HnxDisclosureConnector(),
    SscDisclosureConnector(),
]

@dataclass
class FetchedDocumentRecord:
    ticker: str
    fiscal_year: int | None
    document_type: str
    source_name: str
    source_url: str
    storage_bucket: str
    storage_path: str
    file_hash: str
    content_type: str
    fetched_at: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DiscoveryResult:
    ticker: str
    from_year: int
    to_year: int
    candidates: list[DocumentCandidate]
    ranking: RankingResult
    per_source: dict

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "from_year": self.from_year,
            "to_year": self.to_year,
            "generated_at": datetime.now(UTC).isoformat(),
            "per_source_counts": self.per_source,
            "candidates": [c.to_dict() for c in self.candidates],
            "selected": [c.to_dict() for c in self.ranking.selected],
            "needs_review": [c.to_dict() for c in self.ranking.needs_review],
            "superseded": [c.to_dict() for c in self.ranking.superseded],
        }


def discover_documents(
    ticker: str,
    from_year: int,
    to_year: int,
    *,
    connectors=None,
    http_get=None,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
) -> DiscoveryResult:
    company = get_company(ticker)
    connectors = connectors if connectors is not None else DEFAULT_CONNECTORS
    all_candidates: list[DocumentCandidate] = []
    per_source: dict = {}
    for conn in connectors:
        try:
            found = conn.discover(company, from_year, to_year, http_get=http_get)
        except Exception:  # noqa: BLE001 — a failing connector must not abort discovery
            found = []
        per_source[conn.source_name] = len(found)
        all_candidates.extend(found)

    ranking = rank_candidates(all_candidates, min_confidence=min_confidence)
    return DiscoveryResult(ticker, from_year, to_year, all_candidates, ranking, per_source)


def _default_fetch_bytes(url: str, timeout: int = 60) -> tuple[bytes, str]:
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "maer-doc-fetcher/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (verified TLS)
        return resp.read(), resp.headers.get("Content-Type", "")


def fetch_candidate(
    candidate: DocumentCandidate,
    *,
    fetch_bytes=None,
    storage_adapter=None,
) -> FetchedDocumentRecord:
    """Phase 3B: download and persist an immutable official PDF to Supabase."""
    from backend.storage import SOURCES_BUCKET, SupabaseStorageAdapter, source_document_key

    fetch = fetch_bytes or _default_fetch_bytes
    content, content_type = fetch(candidate.source_url)
    if not content:
        raise RuntimeError(f"empty content for {candidate.source_url}")
    file_hash = hashlib.sha256(content).hexdigest()
    if candidate.fiscal_year is None:
        raise ValueError("Official document fiscal_year is required for canonical storage")
    if "pdf" not in content_type.lower() and not candidate.source_url.lower().endswith(".pdf"):
        raise ValueError("Only immutable PDF official documents may be stored in sources")
    key = source_document_key(candidate.ticker, candidate.fiscal_year, file_hash)
    adapter = storage_adapter or SupabaseStorageAdapter()
    with tempfile.NamedTemporaryFile(suffix=".pdf") as temporary:
        temporary.write(content)
        temporary.flush()
        if adapter.exists(SOURCES_BUCKET, key):
            if not adapter.validate_checksum(SOURCES_BUCKET, key, file_hash):
                raise FileExistsError(f"Checksum conflict: {SOURCES_BUCKET}/{key}")
        else:
            adapter.upload_file(SOURCES_BUCKET, key, temporary.name, "application/pdf")
    return FetchedDocumentRecord(
        ticker=candidate.ticker, fiscal_year=candidate.fiscal_year,
        document_type=candidate.document_type, source_name=candidate.source_name,
        source_url=candidate.source_url, storage_bucket=SOURCES_BUCKET, storage_path=key, file_hash=file_hash,
        content_type=content_type, fetched_at=datetime.now(UTC).isoformat(),
    )
