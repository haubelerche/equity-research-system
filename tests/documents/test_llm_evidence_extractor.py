"""Phase 0: qualitative evidence extraction from annual-report PDFs.

parse_evidence() normalizes the LLM JSON into the evidence_pack shape that
backend.documents.company_research_pack.build_company_research_pack consumes,
so topics become 'covered' (status=observed + evidence_refs) and analyst
insights / company plans are available. Pure function — no LLM in the test.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from backend.documents import llm_evidence_extractor as lee
from backend.documents.company_research_pack import build_company_research_pack


def _fake_client(payload: dict):
    """Minimal stand-in for the OpenAI client used by _complete_json."""
    content = json.dumps(payload)
    message = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=message)
    response = SimpleNamespace(choices=[choice])
    create = lambda **kwargs: response  # noqa: E731
    completions = SimpleNamespace(create=create)
    return SimpleNamespace(chat=SimpleNamespace(completions=completions))


def test_business_topic_becomes_covered_records_with_page_refs():
    raw = {
        "business_topics": {
            "business_segments": [
                {"name": "OTC", "value": "OTC chiếm ~60% doanh thu", "page": 12, "confidence": 0.9},
            ]
        }
    }
    pack = lee.parse_evidence(raw, "DHG", 2025)
    seg = pack["business_evidence"]["business_segments"]
    assert "OTC" in seg
    rec = seg["OTC"]
    assert rec["status"] == "observed"
    assert rec["evidence_refs"] == ["page 12"]
    assert rec["source_class"] == "company"
    assert 0.0 <= rec["confidence"] <= 1.0


def test_catalysts_and_risks_become_lists_with_refs():
    raw = {
        "catalysts": [{"name": "EU-GMP", "value": "Nhà máy đạt EU-GMP 2026", "page": 20}],
        "risks": [{"name": "API cost", "value": "Giá nguyên liệu API tăng", "page": 22}],
    }
    pack = lee.parse_evidence(raw, "DHG", 2025)
    cats = pack["pharma_catalyst_evidence"]["catalysts"]
    risks = pack["business_evidence"]["risks"]
    assert isinstance(cats, list) and cats[0]["evidence_refs"] == ["page 20"]
    assert isinstance(risks, list) and risks[0]["evidence_refs"] == ["page 22"]


def test_borrowing_and_investment_plans_parsed():
    raw = {
        "borrowing_plan": [{"year": 2026, "amount": 0.0, "description": "Không vay mới", "page": 25}],
        "investment_plan": [{"year": 2026, "amount": 200.0, "description": "Dây chuyền mới", "page": 25}],
    }
    pack = lee.parse_evidence(raw, "DHG", 2025)
    bp = pack["company_plans"]["borrowing_plan"]
    ip = pack["company_plans"]["investment_plan"]
    assert bp[0]["year"] == 2026 and bp[0]["amount"] == 0.0 and bp[0]["page"] == 25
    assert ip[0]["amount"] == 200.0


def test_pack_makes_company_research_topics_covered_and_insights_flow():
    raw = {
        "business_topics": {
            "company_profile": [{"name": "overview", "value": "DN dược", "page": 3}],
            "business_segments": [{"name": "OTC", "value": "60% doanh thu", "page": 12}],
            "market_share": [{"name": "share", "value": "Top 1 generic", "page": 14}],
        },
        "catalysts": [{"name": "EU-GMP", "value": "Nhà máy đạt EU-GMP", "page": 20}],
    }
    pack = lee.parse_evidence(raw, "DHG", 2025)
    crp = build_company_research_pack(ticker="DHG", evidence_pack=pack, financial_analysis={})
    missing = crp["coverage"]["missing_topics"]
    assert "company_profile" not in missing
    assert "business_segments" not in missing
    assert "market_share" not in missing
    assert crp["analyst_insights"], "catalysts should produce analyst insights"


def test_extract_evidence_from_pdf_with_fake_client():
    pages = [
        (1, "Tổng quan công ty Dược Hậu Giang"),
        (12, "Cơ cấu doanh thu theo kênh OTC/ETC và thị phần"),
        (25, "Kế hoạch đầu tư và kế hoạch vay vốn năm 2026"),
    ]
    payload = {
        "business_topics": {
            "business_segments": [{"name": "OTC", "value": "OTC ~60%", "page": 12}],
        },
        "catalysts": [{"name": "EU-GMP", "value": "đạt EU-GMP", "page": 25}],
        "borrowing_plan": [{"year": 2026, "amount": 0.0, "description": "Không vay mới", "page": 25}],
    }
    pack = lee.extract_evidence_from_pdf(pages, "DHG", 2025, client=_fake_client(payload))
    assert "business_segments" in pack["business_evidence"]
    assert pack["pharma_catalyst_evidence"]["catalysts"][0]["evidence_refs"] == ["page 25"]
    assert pack["company_plans"]["borrowing_plan"][0]["year"] == 2026


def test_extract_evidence_returns_empty_pack_when_no_pages():
    pack = lee.extract_evidence_from_pdf([], "DHG", 2025, client=_fake_client({}))
    assert pack["business_evidence"] == {}
    assert pack["company_plans"] == {}
