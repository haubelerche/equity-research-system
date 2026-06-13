"""View-model news citations: dedup by article and drop rows that don't name the company.

The report only cites real, relevant articles. Multiple evidence rows from the same
article collapse to one numbered citation; rows whose text never mentions the ticker
or company (e.g. leftover smoke-test data) are excluded.
"""
from __future__ import annotations

from backend.reporting.client_report_view_model import _evidence_to_citations

_KEYWORDS = ("DHG", "Dược Hậu Giang")


def test_dedups_by_url_filters_irrelevant_and_keeps_order() -> None:
    rows = [
        {"source_name": "VnExpress", "title": "DHG báo lãi kỷ lục", "url": "u1",
         "published_at": "2026-06-01", "claim": "DHG lãi lớn"},
        {"source_name": "VnExpress", "title": "DHG báo lãi kỷ lục", "url": "u1",
         "published_at": "2026-06-01", "claim": "biên lợi nhuận cải thiện"},  # same article
        {"source_name": "Vietstock", "title": "", "url": "u2", "published_at": "",
         "claim": "Live whitelisted article fetched into Supabase."},  # smoke / irrelevant
        {"source_name": "CafeF", "title": "Duoc Hau Giang mo rong nha may", "url": "u3",
         "published_at": "2026-05-20", "claim": "đầu tư nhà máy"},
    ]

    cits = _evidence_to_citations(rows, _KEYWORDS)

    assert [c["url"] for c in cits] == ["u1", "u3"]
    assert cits[0]["source_name"] == "VnExpress"
    assert cits[0]["title"] == "DHG báo lãi kỷ lục"
    assert cits[1]["title"] == "Duoc Hau Giang mo rong nha may"


def test_falls_back_to_claim_when_title_missing() -> None:
    rows = [{"source_name": "CafeF", "title": "", "url": "u9", "published_at": "",
             "claim": "DHG chi trả cổ tức tiền mặt"}]
    cits = _evidence_to_citations(rows, _KEYWORDS)
    assert cits[0]["title"] == "DHG chi trả cổ tức tiền mặt"
