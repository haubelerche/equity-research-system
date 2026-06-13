"""Ticker news pipeline: discover → filter to the ticker → fetch → extract evidence.

The pipeline injects all I/O (feed fetch, article fetch, LLM extraction) so it runs
offline and deterministically. Only articles that mention the ticker reach the LLM.
"""
from __future__ import annotations

from backend.news.runner import gather_ticker_evidence
from backend.news.types import EvidenceItem

_RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item><title>DHG báo lãi quý tăng mạnh</title>
        <link>https://cafef.vn/dhg-lai.chn</link></item>
  <item><title>VN-Index đi ngang phiên sáng</title>
        <link>https://cafef.vn/vnindex.chn</link></item>
</channel></rss>"""


def _fetch_xml(url: str) -> str:
    return _RSS


def _fetch_html(url: str) -> str:
    return f"<html><body><article><p>Nội dung bài báo cho {url} về Dược Hậu Giang.</p></article></body></html>"


def _llm_extract(prompt: str) -> object:
    return [
        {
            "claim": "DHG tăng trưởng lợi nhuận nhờ kênh ETC.",
            "evidence_text": "Lợi nhuận quý tăng mạnh.",
            "confidence": "high",
        }
    ]


def test_pipeline_collects_only_ticker_articles_and_extracts_evidence() -> None:
    articles, evidence_by_url = gather_ticker_evidence(
        keywords=("DHG", "Dược Hậu Giang"),
        feeds=[("https://cafef.vn/thi-truong.rss", "rss")],
        fetch_xml=_fetch_xml,
        fetch_html=_fetch_html,
        llm_extract=_llm_extract,
        ticker="DHG",
        company_name="Dược Hậu Giang",
        topic="DHG news",
        max_articles=10,
    )

    # Only the DHG article passes the relevance gate.
    assert [a.source_url for a in articles] == ["https://cafef.vn/dhg-lai.chn"]
    items = evidence_by_url["https://cafef.vn/dhg-lai.chn"]
    assert len(items) == 1
    assert isinstance(items[0], EvidenceItem)
    assert items[0].ticker == "DHG"
    assert items[0].source_name == "CafeF"


def test_skip_urls_excludes_already_processed_articles() -> None:
    # An article already collected (in skip_urls) is not fetched or extracted again.
    articles, evidence_by_url = gather_ticker_evidence(
        keywords=("DHG", "Dược Hậu Giang"),
        feeds=[("https://cafef.vn/thi-truong.rss", "rss")],
        fetch_xml=_fetch_xml,
        fetch_html=_fetch_html,
        llm_extract=_llm_extract,
        ticker="DHG",
        company_name="Dược Hậu Giang",
        topic="DHG news",
        skip_urls={"https://cafef.vn/dhg-lai.chn"},
        max_articles=10,
    )
    assert articles == []
    assert evidence_by_url == {}


def test_pipeline_returns_empty_when_no_article_matches_ticker() -> None:
    articles, evidence_by_url = gather_ticker_evidence(
        keywords=("XYZ",),
        feeds=[("https://cafef.vn/thi-truong.rss", "rss")],
        fetch_xml=_fetch_xml,
        fetch_html=_fetch_html,
        llm_extract=_llm_extract,
        ticker="XYZ",
        company_name="Khong Co",
        topic="x",
        max_articles=10,
    )
    assert articles == []
    assert evidence_by_url == {}
