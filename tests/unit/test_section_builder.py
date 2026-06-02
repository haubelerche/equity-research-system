"""Tests for backend/reporting/section_builder.py — TDD, run before implementation."""
import pytest
from dataclasses import field

from backend.reporting.section_builder import (
    ReportContext,
    build_report_sections,
    assemble_markdown,
    _chart_ref,
    _build_valuation_bridge_md,
)

EXPECTED_PAGE_IDS = [
    "cover_snapshot",
    "company_overview",
    "financial_performance",
    "forecast_assumptions",
    "valuation",
    "sensitivity_peer",
    "catalysts_risks",
    "conclusion",
]


def _minimal_ctx(**kwargs) -> ReportContext:
    defaults = dict(
        ticker="DHG",
        company_name="DHG Pharma",
        exchange="HOSE",
        report_date="2026-06-01",
        data_cutoff="2025-12-31",
        rating="BUY",
        current_price=94400.0,
        target_price=137010.0,
        upside_pct=45.1,
        risk_level="MEDIUM",
        data_confidence="HIGH",
        status="DRAFT",
    )
    defaults.update(kwargs)
    return ReportContext(**defaults)


# ---------------------------------------------------------------------------
# Structural tests
# ---------------------------------------------------------------------------

def test_build_sections_returns_8():
    ctx = _minimal_ctx()
    sections = build_report_sections(ctx)
    assert len(sections) == 8


def test_section_page_identifiers():
    ctx = _minimal_ctx()
    sections = build_report_sections(ctx)
    ids = [s["page"] for s in sections]
    assert ids == EXPECTED_PAGE_IDS


def test_section_dicts_have_required_keys():
    ctx = _minimal_ctx()
    sections = build_report_sections(ctx)
    for s in sections:
        assert "page" in s
        assert "page_number" in s
        assert "title" in s
        assert "markdown" in s
        assert "chart_ids" in s
        assert "word_count" in s


def test_page_numbers_are_1_to_8():
    ctx = _minimal_ctx()
    sections = build_report_sections(ctx)
    numbers = [s["page_number"] for s in sections]
    assert numbers == list(range(1, 9))


# ---------------------------------------------------------------------------
# Page 1 � cover_snapshot
# ---------------------------------------------------------------------------

def test_page_1_has_price_rating():
    ctx = _minimal_ctx(
        current_price=94400.0,
        target_price=137010.0,
        upside_pct=45.1,
        rating="BUY",
    )
    sections = build_report_sections(ctx)
    page1 = sections[0]
    assert page1["page"] == "cover_snapshot"
    md = page1["markdown"]
    assert "94,400" in md, f"current_price not found with commas in: {md[:400]}"
    assert "137,010" in md, f"target_price not found with commas in: {md[:400]}"
    assert "+45.1%" in md, f"upside not found in: {md[:400]}"
    assert "BUY" in md, f"rating not found in: {md[:400]}"


def test_page_1_contains_ticker():
    ctx = _minimal_ctx(ticker="DHG")
    sections = build_report_sections(ctx)
    assert "DHG" in sections[0]["markdown"]


def test_page_1_has_investment_thesis_placeholder_when_empty():
    ctx = _minimal_ctx(investment_thesis="")
    sections = build_report_sections(ctx)
    md = sections[0]["markdown"]
    # Should render the Vietnamese placeholder when thesis is empty
    assert "Nội dung chưa có" in md or "[Nội dung chưa có]" in md


def test_page_1_has_investment_thesis_when_provided():
    ctx = _minimal_ctx(investment_thesis="DHG dẫn đầu thị phần dược phẩm miền Nam.")
    sections = build_report_sections(ctx)
    assert "DHG dẫn đầu thị phần dược phẩm miền Nam." in sections[0]["markdown"]


def test_page_1_rating_under_review():
    ctx = _minimal_ctx(rating="UNDER_REVIEW")
    sections = build_report_sections(ctx)
    assert "UNDER_REVIEW" in sections[0]["markdown"]


# ---------------------------------------------------------------------------
# Page 8 � conclusion / disclaimer
# ---------------------------------------------------------------------------

def test_page_8_has_disclaimer():
    ctx = _minimal_ctx()
    sections = build_report_sections(ctx)
    page8 = sections[7]
    assert page8["page"] == "conclusion"
    md = page8["markdown"]
    assert "khuyến nghị đầu tư cá nhân hóa" in md


def test_page_8_disclaimer_full_text():
    ctx = _minimal_ctx()
    sections = build_report_sections(ctx)
    md = sections[7]["markdown"]
    assert "không phải lời mời mua/bán chứng khoán" in md
    assert "chuyên gia được cấp phép" in md


# ---------------------------------------------------------------------------
# assemble_markdown
# ---------------------------------------------------------------------------

def test_assemble_markdown_has_7_pagebreaks():
    ctx = _minimal_ctx()
    sections = build_report_sections(ctx)
    assembled = assemble_markdown(sections)
    count = assembled.count("\\pagebreak")
    assert count == 7, f"Expected 7 pagebreaks, got {count}"


def test_assemble_markdown_returns_string():
    ctx = _minimal_ctx()
    sections = build_report_sections(ctx)
    result = assemble_markdown(sections)
    assert isinstance(result, str)
    assert len(result) > 100


def test_assemble_markdown_preserves_all_section_content():
    ctx = _minimal_ctx(ticker="TESTICK")
    sections = build_report_sections(ctx)
    assembled = assemble_markdown(sections)
    # Every section's markdown should appear in the assembled output
    for s in sections:
        # Check at least the first 50 chars of each section appear
        snippet = s["markdown"][:50].strip()
        if snippet:
            assert snippet in assembled


# ---------------------------------------------------------------------------
# _chart_ref helper
# ---------------------------------------------------------------------------

def test_chart_ref_with_path():
    ctx = _minimal_ctx(chart_paths={"C2": "artifacts/charts/DHG_C2.png"})
    result = _chart_ref(ctx, "C2")
    assert result == "![C2](artifacts/charts/DHG_C2.png)"


def test_chart_ref_without_path():
    ctx = _minimal_ctx(chart_paths={})
    result = _chart_ref(ctx, "C2")
    # Should return a blockquote-style placeholder
    assert result.startswith(">"), f"Expected blockquote, got: {result}"


def test_chart_ref_with_fallback_note():
    ctx = _minimal_ctx(chart_paths={})
    result = _chart_ref(ctx, "C99", fallback_note="Chart not generated")
    assert "Chart not generated" in result
    assert result.startswith(">")


def test_chart_ref_unknown_id_with_paths_dict():
    # chart_paths exists but doesn't contain the requested ID
    ctx = _minimal_ctx(chart_paths={"C1": "artifacts/charts/DHG_C1.png"})
    result = _chart_ref(ctx, "C99")
    assert result.startswith(">")


# ---------------------------------------------------------------------------
# word_count sanity
# ---------------------------------------------------------------------------

def test_word_count_is_non_negative_int():
    ctx = _minimal_ctx()
    sections = build_report_sections(ctx)
    for s in sections:
        assert isinstance(s["word_count"], int)
        assert s["word_count"] >= 0


# ---------------------------------------------------------------------------
# chart_ids are lists
# ---------------------------------------------------------------------------

def test_chart_ids_are_lists():
    ctx = _minimal_ctx()
    sections = build_report_sections(ctx)
    for s in sections:
        assert isinstance(s["chart_ids"], list)


# ---------------------------------------------------------------------------
# New tests — valuation_bridge and citation_appendix fields
# ---------------------------------------------------------------------------

def test_valuation_bridge_field_in_context():
    """ReportContext accepts valuation_bridge field."""
    ctx = _minimal_ctx(valuation_bridge="## Some Bridge\n\nContent here.")
    assert ctx.valuation_bridge == "## Some Bridge\n\nContent here."


def test_valuation_section_includes_bridge_when_set():
    """_build_valuation output contains the bridge text when valuation_bridge is set."""
    ctx = _minimal_ctx(valuation_bridge="MY_BRIDGE_MARKER")
    sections = build_report_sections(ctx)
    val_section = next(s for s in sections if s["page"] == "valuation")
    assert "MY_BRIDGE_MARKER" in val_section["markdown"]
    assert "Valuation Bridge" in val_section["markdown"]


def test_valuation_section_no_bridge_when_empty():
    """No 'Valuation Bridge' header appears when valuation_bridge is empty."""
    ctx = _minimal_ctx(valuation_bridge="")
    sections = build_report_sections(ctx)
    val_section = next(s for s in sections if s["page"] == "valuation")
    assert "Valuation Bridge" not in val_section["markdown"]


def test_build_valuation_bridge_md_all_values():
    """_build_valuation_bridge_md returns markdown with expected headings for full input."""
    md = _build_valuation_bridge_md(
        sum_pv_fcff=1200.5,
        pv_tv_fcff=3500.0,
        ev_fcff=4700.5,
        net_debt=500.0,
        equity_value_fcff=4200.5,
        shares_mn=43.8,
        price_fcff=95890.0,
        sum_pv_fcfe=800.0,
        pv_tv_fcfe=2200.0,
        equity_value_fcfe=3000.0,
        price_fcfe=68493.0,
        target_price=85000.0,
        current_price=70000.0,
    )
    assert "### FCFF Bridge" in md
    assert "### FCFE Bridge" in md
    assert "### Giá mục tiêu gộp" in md
    assert "Price_FCFF" in md
    assert "Price_FCFE" in md
    assert "Target Price" in md
    assert "Tiềm năng tăng/giảm" in md
    # Check a formatted number appears
    assert "1,200.5" in md


def test_build_valuation_bridge_md_none_values():
    """None inputs produce '—' not a crash."""
    md = _build_valuation_bridge_md(
        sum_pv_fcff=None,
        pv_tv_fcff=None,
        ev_fcff=None,
        net_debt=None,
        equity_value_fcff=None,
        shares_mn=None,
        price_fcff=None,
        sum_pv_fcfe=None,
        pv_tv_fcfe=None,
        equity_value_fcfe=None,
        price_fcfe=None,
        target_price=None,
        current_price=None,
    )
    assert "—" in md
    assert "### FCFF Bridge" in md
    assert "### FCFE Bridge" in md
    assert "### Giá mục tiêu gộp" in md


def test_citation_appendix_in_conclusion():
    """Conclusion section includes citation appendix when field is set."""
    ctx = _minimal_ctx(citation_appendix="[C1] Source: DHG Annual Report 2024")
    sections = build_report_sections(ctx)
    conclusion = next(s for s in sections if s["page"] == "conclusion")
    assert "[C1] Source: DHG Annual Report 2024" in conclusion["markdown"]
    assert "Phụ lục Citation" in conclusion["markdown"]


def test_citation_appendix_absent_when_empty():
    """No 'Phụ lục Citation' header when citation_appendix is empty."""
    ctx = _minimal_ctx(citation_appendix="")
    sections = build_report_sections(ctx)
    conclusion = next(s for s in sections if s["page"] == "conclusion")
    assert "Phụ lục Citation" not in conclusion["markdown"]
