"""AGM (ĐHCĐ) extractor — parse the two-layer resolution/driver pack.

parse_agm() normalizes the LLM JSON into the agm_pack shape: approved_resolutions
(what shareholders approved) plus the forward drivers dug out of the backing
tờ trình/báo cáo (targets_2026, dividend/borrowing/investment plans, R&D + product
focus, management direction). Pure function — no LLM in these tests.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from backend.documents import agm_extractor as ax


def _fake_client(payload: dict):
    content = json.dumps(payload)
    message = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=message)
    response = SimpleNamespace(choices=[choice])
    create = lambda **kwargs: response  # noqa: E731
    completions = SimpleNamespace(create=create)
    return SimpleNamespace(chat=SimpleNamespace(completions=completions))


def test_approved_resolutions_parsed():
    raw = {
        "approved_resolutions": [
            {"item_no": "1", "title": "Thông qua KQKD 2025", "summary": "Doanh thu 5000 tỷ", "page": 2},
            {"item_no": "2", "title": "Kế hoạch 2026", "summary": "Mục tiêu tăng 10%", "page": 3},
        ]
    }
    pack = ax.parse_agm(raw, "DHG", 2026)
    res = pack["approved_resolutions"]
    assert len(res) == 2
    assert res[0]["item_no"] == "1" and res[0]["page"] == 2
    assert res[0]["status"] == "observed"


def test_targets_2026_parsed():
    raw = {"targets_2026": {"revenue": 5500.0, "npat": 1100.0, "revenue_growth_pct": 10.0, "page": 3}}
    pack = ax.parse_agm(raw, "DHG", 2026)
    t = pack["targets_2026"]
    assert t["revenue"] == 5500.0 and t["npat"] == 1100.0
    assert t["revenue_growth_pct"] == 10.0 and t["page"] == 3


def test_borrowing_and_investment_plans_parsed_with_linked_resolution():
    raw = {
        "borrowing_plan": [
            {"year": 2026, "amount": 300.0, "description": "Vay đầu tư nhà máy", "page": 8, "linked_resolution": "5"},
        ],
        "investment_plan": [
            {"year": 2026, "amount": 500.0, "description": "Xây nhà máy Non-betalactam", "page": 8, "linked_resolution": "5"},
        ],
    }
    pack = ax.parse_agm(raw, "DHG", 2026)
    bp = pack["borrowing_plan"][0]
    ip = pack["investment_plan"][0]
    assert bp["year"] == 2026 and bp["amount"] == 300.0 and bp["linked_resolution"] == "5"
    assert ip["amount"] == 500.0 and ip["page"] == 8


def test_dividend_plan_parsed():
    raw = {"dividend_plan": [{"year": 2026, "cash_per_share": 2500.0, "payout_pct": 25.0, "page": 4}]}
    pack = ax.parse_agm(raw, "DHG", 2026)
    d = pack["dividend_plan"][0]
    assert d["cash_per_share"] == 2500.0 and d["payout_pct"] == 25.0


def test_rnd_and_business_direction_parsed():
    raw = {
        "rnd_and_product_focus": [{"name": "Đông dược", "description": "Tập trung sản phẩm đông dược", "page": 6}],
        "business_direction": [{"name": "Mở rộng ETC", "value": "Đẩy mạnh kênh bệnh viện", "page": 5}],
    }
    pack = ax.parse_agm(raw, "DHG", 2026)
    assert pack["rnd_and_product_focus"][0]["name"] == "Đông dược"
    assert pack["business_direction"][0]["value"] == "Đẩy mạnh kênh bệnh viện"


def test_empty_raw_yields_wellformed_empty_pack():
    pack = ax.parse_agm({}, "DHG", 2026)
    assert pack["ticker"] == "DHG" and pack["meeting_year"] == 2026
    assert pack["approved_resolutions"] == []
    assert pack["targets_2026"] == {}
    assert pack["borrowing_plan"] == []


def test_malformed_list_items_skipped():
    raw = {"borrowing_plan": ["not a dict", {"year": 2026, "amount": 100.0, "page": 9}]}
    pack = ax.parse_agm(raw, "DHG", 2026)
    assert len(pack["borrowing_plan"]) == 1
    assert pack["borrowing_plan"][0]["amount"] == 100.0


def test_extract_agm_from_pdf_with_fake_client():
    pages = [
        (2, "NGHỊ QUYẾT đại hội đồng cổ đông thường niên 2026"),
        (3, "Tờ trình kế hoạch kinh doanh năm 2026, mục tiêu doanh thu"),
        (8, "Phương án vay vốn và kế hoạch đầu tư xây dựng nhà máy"),
    ]
    payload = {
        "approved_resolutions": [{"item_no": "1", "title": "KH 2026", "page": 2}],
        "targets_2026": {"revenue": 5500.0, "revenue_growth_pct": 10.0, "page": 3},
        "borrowing_plan": [{"year": 2026, "amount": 300.0, "description": "Vay nhà máy", "page": 8}],
    }
    pack = ax.extract_agm_from_pdf(pages, "DHG", 2026, client=_fake_client(payload))
    assert pack["approved_resolutions"][0]["item_no"] == "1"
    assert pack["targets_2026"]["revenue"] == 5500.0
    assert pack["borrowing_plan"][0]["amount"] == 300.0


def test_extract_agm_returns_empty_pack_when_no_pages():
    pack = ax.extract_agm_from_pdf([], "DHG", 2026, client=_fake_client({}))
    assert pack["approved_resolutions"] == []
    assert pack["borrowing_plan"] == []


def test_system_prompt_is_bilingual_and_demands_numeric_targets():
    # Docs mix Vietnamese (báo cáo/kế hoạch) and English (resolutions, e.g. DHG).
    prompt = ax.build_agm_system_prompt()
    assert "English" in prompt or "tiếng Anh" in prompt
    # Must force the numeric 2026 business-plan + prior-year-actual digging.
    assert "kế hoạch kinh doanh" in prompt.lower()
    assert "doanh thu" in prompt.lower() and "lợi nhuận" in prompt.lower()
