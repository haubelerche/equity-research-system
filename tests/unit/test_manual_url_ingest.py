"""Manual URL ingest: fetch + extract + build evidence for human-vetted article URLs.

Uses the citation allowlist (wider than discovery), de-dupes, and rejects URLs outside
the allowlist. I/O is injected so the test is offline and deterministic.
"""
from __future__ import annotations

from backend.news.runner import ingest_manual_urls
from backend.news.types import EvidenceItem


def _fetch_html(url: str) -> str:
    return (
        "<html><body><article><h1>DHG quý I/2026</h1>"
        "<p>Dược Hậu Giang đạt LNST 315,7 tỷ đồng, tăng hơn 18%.</p>"
        "</article></body></html>"
    )


def _llm(_prompt: str) -> object:
    return [{"claim": "DHG lãi tăng hơn 18%.", "evidence_text": "LNST 315,7 tỷ đồng."}]


def test_ingests_citable_url_and_builds_evidence() -> None:
    articles, evidence = ingest_manual_urls(
        urls=["https://www.tinnhanhchungkhoan.vn/dhg-q1-post389927.html"],
        ticker="DHG",
        company_name="Dược Hậu Giang",
        topic="Tin tức DHG",
        fetch_html=_fetch_html,
        llm_extract=_llm,
    )
    assert [a.source_url for a in articles] == [
        "https://www.tinnhanhchungkhoan.vn/dhg-q1-post389927.html"
    ]
    assert articles[0].source_name == "Tin nhanh Chứng khoán"
    assert articles[0].discovery_method == "manual_url"
    items = evidence["https://www.tinnhanhchungkhoan.vn/dhg-q1-post389927.html"]
    assert len(items) == 1
    assert isinstance(items[0], EvidenceItem)
    assert items[0].ticker == "DHG"


def test_rejects_url_outside_citation_allowlist() -> None:
    articles, evidence = ingest_manual_urls(
        urls=["https://evil.example.com/dhg"],
        ticker="DHG",
        company_name="Dược Hậu Giang",
        topic="x",
        fetch_html=_fetch_html,
        llm_extract=_llm,
    )
    assert articles == []
    assert evidence == {}
