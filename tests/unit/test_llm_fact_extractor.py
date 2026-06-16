"""Tests for backend.documents.llm_fact_extractor — pure parsing/validation + a
mocked end-to-end extract_facts call (no real LLM)."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from backend.documents import llm_fact_extractor as lfe


VALID = lfe.allowed_codes(lfe._FALLBACK_CATALOG)


def test_allowed_codes_has_cashflow_keys_for_fcfe():
    # The FCFE blocker root cause was these CFS keys being unregistered.
    assert {"proceeds_from_borrowings.total", "repayment_of_borrowings.total",
            "operating_cash_flow.total", "capex.total"} <= VALID


def test_parse_keeps_valid_metric_and_normalises_value():
    raw = {"facts": [
        {"metric": "revenue.net", "value": 419.496, "page": 14, "source_label": "Doanh thu thuần", "confidence": 0.9},
    ]}
    facts = lfe.parse_llm_facts(raw, "AGP", 2022, VALID)
    assert len(facts) == 1
    assert facts[0].metric == "revenue.net"
    assert facts[0].value == pytest.approx(419.496)
    assert facts[0].period == "2022FY"
    assert facts[0].page_number == 14


def test_parse_drops_unknown_metric():
    raw = {"facts": [{"metric": "charter_capital.ending", "value": 22.0, "confidence": 0.9}]}
    assert lfe.parse_llm_facts(raw, "AGP", 2022, VALID) == []


def test_parse_drops_year_number_mistaken_as_value():
    # The exact AGP bug: 2008 (a year) parsed as a financial value.
    raw = {"facts": [{"metric": "revenue.net", "value": 2008, "confidence": 0.8}]}
    assert lfe.parse_llm_facts(raw, "AGP", 2024, VALID) == []


def test_parse_keeps_whole_number_value():
    # Real BCTC figures are often round (e.g. 200 tỷ). The LLM is told to skip
    # Mã-số codes, so we no longer drop whole numbers in 1..999 — only years.
    raw = {"facts": [{"metric": "gross_profit.total", "value": 200, "confidence": 0.8}]}
    facts = lfe.parse_llm_facts(raw, "AGP", 2022, VALID)
    assert len(facts) == 1 and facts[0].value == 200


def test_parse_allows_shares_outstanding_integer():
    raw = {"facts": [{"metric": "shares_outstanding.ending", "value": 22000000, "confidence": 0.9}]}
    facts = lfe.parse_llm_facts(raw, "AGP", 2022, VALID)
    assert len(facts) == 1 and facts[0].value == 22000000


def test_parse_dedupes_by_metric_keeping_highest_confidence():
    raw = {"facts": [
        {"metric": "revenue.net", "value": 100.0, "confidence": 0.6},
        {"metric": "revenue.net", "value": 419.5, "confidence": 0.95},
    ]}
    facts = lfe.parse_llm_facts(raw, "AGP", 2022, VALID)
    assert len(facts) == 1 and facts[0].value == pytest.approx(419.5)


def test_parse_negative_parentheses():
    raw = {"facts": [{"metric": "financing_cash_flow.total", "value": "(273.6)", "confidence": 0.8}]}
    facts = lfe.parse_llm_facts(raw, "AGP", 2022, VALID)
    assert len(facts) == 1 and facts[0].value == pytest.approx(-273.6)


def test_coerce_number_vietnamese_separators():
    assert lfe._coerce_number("1.234,5") == pytest.approx(1234.5)
    assert lfe._coerce_number("4,127") == pytest.approx(4127)
    assert lfe._coerce_number("abc") is None


def test_select_financial_pages_picks_statement_pages_with_context():
    pages = [
        (1, "Trang bìa báo cáo thường niên"),
        (10, "BẢNG CÂN ĐỐI KẾ TOÁN\nTài sản ngắn hạn ..."),
        (11, "tiếp theo bảng cân đối"),
        (40, "Nội dung không liên quan"),
        (55, "BÁO CÁO LƯU CHUYỂN TIỀN TỆ"),
    ]
    selected = {n for n, _ in lfe.select_financial_pages(pages, context=1)}
    assert 10 in selected and 11 in selected and 55 in selected
    assert 1 not in selected and 40 not in selected


def test_select_financial_pages_fallback_when_no_header():
    pages = [(i, "lorem ipsum") for i in range(1, 40)]
    selected = lfe.select_financial_pages(pages, max_pages=5)
    assert len(selected) == 5


def test_required_facts_union_has_fcfe_and_fcff_keys():
    req = lfe.required_facts_union()
    assert {"proceeds_from_borrowings.total", "repayment_of_borrowings.total",
            "capex.total", "operating_cash_flow.total", "shares_outstanding.ending",
            "revenue.net"} <= req


def test_catalog_for_statement_groups_by_type_with_extras():
    bs = {r["line_item_code"] for r in lfe.catalog_for_statement("balance_sheet", lfe._FALLBACK_CATALOG)}
    assert "total_assets.ending" in bs and "cash_and_equivalents.ending" in bs
    assert "revenue.net" not in bs
    # depreciation is cross-listed into the cash-flow pass (indirect method)
    cfs = {r["line_item_code"] for r in lfe.catalog_for_statement("cash_flow", lfe._FALLBACK_CATALOG)}
    assert {"operating_cash_flow.total", "capex.total", "depreciation.total"} <= cfs


def test_select_pages_for_one_statement_only():
    pages = [
        (10, "BẢNG CÂN ĐỐI KẾ TOÁN\nTài sản ngắn hạn"),
        (30, "BÁO CÁO LƯU CHUYỂN TIỀN TỆ\nTiền thu từ đi vay"),
    ]
    bs = {n for n, _ in lfe.select_financial_pages(pages, statement="balance_sheet")}
    assert bs == {10}
    cfs = {n for n, _ in lfe.select_financial_pages(pages, statement="cash_flow")}
    assert cfs == {30}


def test_select_pages_targeted_returns_empty_when_no_header():
    # Targeted pass returns [] (not a fallback dump) so the caller decides.
    pages = [(i, "noise") for i in range(1, 10)]
    assert lfe.select_financial_pages(pages, statement="cash_flow") == []


def test_select_note_pages_finds_borrowings_note():
    pages = [
        (32, "8. Vay và nợ thuê tài chính dài hạn ..."),
        (49, "Vay ngắn hạn ngân hàng 106.558.000.000"),
        (60, "noise"),
    ]
    note = {n for n, _ in lfe.select_note_pages(pages, "balance_sheet")}
    assert 49 in note  # short-term borrowings note pulled in
    assert 60 not in note
    # No note keywords configured for cash_flow → empty.
    assert lfe.select_note_pages(pages, "cash_flow") == []


def test_build_statement_prompt_marks_required():
    subset = lfe.catalog_for_statement("cash_flow", lfe._FALLBACK_CATALOG)
    prompt = lfe.build_statement_system_prompt("cash_flow", subset, lfe.required_facts_union())
    assert "proceeds_from_borrowings.total" in prompt and "[BẮT BUỘC]" in prompt


def test_extract_facts_targeted_merges_three_passes():
    # One pass per statement; each returns its own metric. Merge = union.
    responses = {
        "balance_sheet": {"facts": [{"metric": "total_assets.ending", "value": 802.4, "confidence": 0.9}]},
        "income_statement": {"facts": [{"metric": "revenue.net", "value": 687.0, "confidence": 0.9}]},
        "cash_flow": {"facts": [{"metric": "operating_cash_flow.total", "value": 25.5, "confidence": 0.9}]},
    }

    calls: list[str] = []

    def _create(**kwargs):
        sys_txt = kwargs["messages"][0]["content"]
        calls.append(sys_txt)
        content = json.dumps({"facts": []})
        for stmt, vi in lfe._STATEMENT_VI.items():
            if vi in sys_txt:
                content = json.dumps(responses[stmt])
                break
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=_create))
    )
    pages = [
        (10, "BẢNG CÂN ĐỐI KẾ TOÁN\nTài sản"),
        (14, "BÁO CÁO KẾT QUẢ HOẠT ĐỘNG KINH DOANH\nDoanh thu thuần"),
        (20, "BÁO CÁO LƯU CHUYỂN TIỀN TỆ\nLưu chuyển tiền thuần"),
    ]
    facts = lfe.extract_facts_targeted(pages, "AGP", 2022, client=client, catalog=lfe._FALLBACK_CATALOG)
    assert len(calls) == 3
    assert {f.metric for f in facts} == {"total_assets.ending", "revenue.net", "operating_cash_flow.total"}


def test_extract_facts_with_mocked_client():
    payload = {"facts": [
        {"metric": "revenue.net", "value": 419.5, "page": 14, "source_label": "Doanh thu thuần", "confidence": 0.9},
        {"metric": "net_income.parent", "value": 32.4, "page": 14, "source_label": "LNST", "confidence": 0.9},
        {"metric": "2008", "value": 2008, "confidence": 0.5},  # junk, dropped
    ]}

    class _Resp:
        choices = [SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))]

    class _Client:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    assert kwargs["response_format"] == {"type": "json_object"}
                    return _Resp()

    pages = [(14, "BÁO CÁO KẾT QUẢ HOẠT ĐỘNG KINH DOANH\nDoanh thu thuần 419.5")]
    facts = lfe.extract_facts(pages, "AGP", 2022, client=_Client(), catalog=lfe._FALLBACK_CATALOG)
    metrics = {f.metric for f in facts}
    assert metrics == {"revenue.net", "net_income.parent"}
