"""Phase 5 — document fetcher stores raw_content_hash (no network)."""
from __future__ import annotations

import pytest

from backend.sources.document_fetcher import FetchError, fetch_document
from backend.sources.document_store import compute_hash
from backend.sources.source_registry import RegisteredSource


def _http_source():
    return RegisteredSource(
        name="hnx_disclosure", source_type="exchange_disclosure", source_tier=0,
        base_url="https://www.hnx.vn", allowed_event_types=["financial_disclosure"],
        fetch_method="http", enabled=True,
    )


def _manual_source():
    return RegisteredSource(
        name="broker_research", source_type="broker_report", source_tier=2,
        base_url="https://x", allowed_event_types=["broker_report"],
        fetch_method="manual", enabled=True,
    )


# 3. Fetched document stores raw_content_hash
def test_fetch_stores_content_hash(tmp_path):
    payload = b"<html>DHG disclosure body</html>"
    doc = fetch_document(
        _http_source(), "https://www.hnx.vn/doc/1", "DHG disclosure",
        fetch_fn=lambda url: payload, store_root=tmp_path,
    )
    assert doc.raw_content_hash == compute_hash(payload)
    assert doc.local_path
    from pathlib import Path
    assert Path(doc.local_path).exists()


def test_manual_fetch_requires_local_file(tmp_path):
    with pytest.raises(FetchError):
        fetch_document(_manual_source(), "https://x/doc", "t", store_root=tmp_path)


def test_manual_fetch_reads_local_file(tmp_path):
    f = tmp_path / "doc.bin"
    f.write_bytes(b"broker report bytes")
    doc = fetch_document(_manual_source(), "https://x/doc", "Broker report",
                         local_file=f, store_root=tmp_path)
    assert doc.raw_content_hash == compute_hash(b"broker report bytes")


def test_disabled_source_refuses_fetch(tmp_path):
    src = _http_source()
    src.enabled = False
    with pytest.raises(FetchError):
        fetch_document(src, "https://x", "t", fetch_fn=lambda u: b"x", store_root=tmp_path)
