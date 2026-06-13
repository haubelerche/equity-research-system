"""build_evidence honours an allowed_domains override (for manual citation ingest).

By default evidence is only built from the four discovery domains. Manual ingest passes
the wider citation allowlist so a human-vetted reputable-media article yields evidence.
"""
from __future__ import annotations

from backend.news.evidence_builder import build_evidence
from backend.news.types import CITATION_ALLOWED_DOMAINS, RawArticle


def _article() -> RawArticle:
    return RawArticle(
        source_name="Tin nhanh Chứng khoán",
        source_domain="tinnhanhchungkhoan.vn",
        source_url="https://www.tinnhanhchungkhoan.vn/dhg-q1-post389927.html",
        title="DHG quý I/2026",
        raw_text="DHG đạt LNST 315,7 tỷ đồng, tăng hơn 18%.",
    )


def _llm(_prompt: str) -> object:
    return [{"claim": "DHG lãi tăng hơn 18%.", "evidence_text": "LNST 315,7 tỷ đồng."}]


def test_reputable_media_rejected_under_default_discovery_whitelist() -> None:
    assert build_evidence(_article(), llm_extract=_llm, ticker="DHG") == []


def test_reputable_media_allowed_under_citation_whitelist() -> None:
    items = build_evidence(
        _article(),
        llm_extract=_llm,
        ticker="DHG",
        allowed_domains=CITATION_ALLOWED_DOMAINS,
    )
    assert len(items) == 1
    assert items[0].ticker == "DHG"
    assert items[0].source_name == "Tin nhanh Chứng khoán"
