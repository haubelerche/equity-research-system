"""Unit tests for backend.reporting.html_renderer.HTMLRenderer."""
from __future__ import annotations

import pytest

from backend.reporting.section_builder import ReportContext, build_report_sections
from backend.reporting.html_renderer import HTMLRenderer


# -- Shared fixture ------------------------------------------------------------

def _make_ctx() -> ReportContext:
    return ReportContext(
        ticker="DHG",
        company_name="Du?c H?u Giang",
        exchange="HOSE",
        report_date="2026-06-01",
        data_cutoff="2025-12-31",
        rating="UNDER_REVIEW",
        current_price=94_400,
        target_price=137_010,
        upside_pct=45.1,
        risk_level="Cao",
        data_confidence="Medium",
        status="NEEDS_REVIEW",
    )


# -- Tests ---------------------------------------------------------------------

def test_html_renderer_creates_html_file(tmp_path):
    """render() must create a file with .html suffix containing DOCTYPE and ticker."""
    ctx = _make_ctx()
    sections = build_report_sections(ctx)
    out = HTMLRenderer().render(sections, ctx, output_dir=tmp_path)

    assert out.exists(), "Output file was not created"
    assert out.suffix == ".html", f"Expected .html suffix, got {out.suffix!r}"

    content = out.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in content
    assert "DHG" in content


def test_html_contains_disclaimer(tmp_path):
    """The disclaimer phrase must appear in the rendered HTML."""
    ctx = _make_ctx()
    sections = build_report_sections(ctx)
    content = HTMLRenderer().render(sections, ctx, output_dir=tmp_path).read_text(encoding="utf-8")

    assert "khuyến nghị đầu tư cá nhân hóa" in content, (
        "Disclaimer phrase not found in rendered HTML"
    )


def test_html_has_8_sections(tmp_path):
    """There must be exactly 8 report-section divs."""
    ctx = _make_ctx()
    sections = build_report_sections(ctx)
    content = HTMLRenderer().render(sections, ctx, output_dir=tmp_path).read_text(encoding="utf-8")

    count = content.count('class="report-section"')
    assert count == 8, f"Expected 8 report-section divs, found {count}"


def test_html_has_page_breaks(tmp_path):
    """Logical sections must not receive unconditional physical page breaks."""
    ctx = _make_ctx()
    sections = build_report_sections(ctx)
    content = HTMLRenderer().render(sections, ctx, output_dir=tmp_path).read_text(encoding="utf-8")

    count = content.count('class="page-break"')
    assert count == 0, f"Expected no unconditional page-break divs, found {count}"


def test_output_filename_with_run_id(tmp_path):
    """When run_id is given the filename should start with '{run_id}_{ticker}'."""
    ctx = _make_ctx()
    sections = build_report_sections(ctx)
    out = HTMLRenderer().render(sections, ctx, output_dir=tmp_path, run_id="RUN_001")

    assert out.name.startswith("RUN_001_DHG"), (
        f"Expected filename starting with 'RUN_001_DHG', got {out.name!r}"
    )


def test_output_filename_without_run_id(tmp_path):
    """When run_id is empty the filename should be exactly 'DHG_report.html'."""
    ctx = _make_ctx()
    sections = build_report_sections(ctx)
    out = HTMLRenderer().render(sections, ctx, output_dir=tmp_path, run_id="")

    assert out.name == "DHG_report.html", (
        f"Expected 'DHG_report.html', got {out.name!r}"
    )


def test_html_is_valid_utf8(tmp_path):
    """The HTML file must be valid UTF-8 (no encode errors for Vietnamese text)."""
    ctx = _make_ctx()
    sections = build_report_sections(ctx)
    out = HTMLRenderer().render(sections, ctx, output_dir=tmp_path)
    # If read_text with utf-8 succeeds without exception the file is valid UTF-8
    content = out.read_text(encoding="utf-8")
    assert len(content) > 0


def test_output_dir_created_if_missing(tmp_path):
    """render() must create the output directory if it does not exist."""
    nested = tmp_path / "deep" / "nested" / "dir"
    assert not nested.exists()

    ctx = _make_ctx()
    sections = build_report_sections(ctx)
    out = HTMLRenderer().render(sections, ctx, output_dir=nested)

    assert nested.exists()
    assert out.exists()


def test_client_final_mode_hides_internal_status_banner(tmp_path):
    """render(render_mode='client_final') must not render the draft/needs-review banner."""
    ctx = _make_ctx()  # ctx.status == "NEEDS_REVIEW"
    sections = build_report_sections(ctx)
    content = HTMLRenderer().render(
        sections, ctx, output_dir=tmp_path, render_mode="client_final"
    ).read_text(encoding="utf-8")

    # The status banner div must not appear (CSS class definition is OK)
    assert '<div class="draft-banner">' not in content, (
        "Internal draft-banner div must not appear in client_final HTML output"
    )
    assert "BÁO CÁO NHÁP (DRAFT)" not in content, (
        "Internal draft notice must not appear in client_final HTML output"
    )
    # The raw status value "NEEDS_REVIEW" must not be placed in the status template var
    # (it may still appear in section text from quality tables, but not from the status banner)
    assert "NEEDS_REVIEW" not in content, (
        "NEEDS_REVIEW must not appear in client_final HTML output"
    )


def test_default_mode_does_not_render_internal_status_banner(tmp_path):
    """The report template must not render the former draft-warning banner in any mode."""
    ctx = _make_ctx()
    sections = build_report_sections(ctx)
    content = HTMLRenderer().render(
        sections, ctx, output_dir=tmp_path
    ).read_text(encoding="utf-8")

    assert '<div class="draft-banner">' not in content
    assert "BÁO CÁO NHÁP" not in content
    assert "Không xuất bản chính thức" not in content
    assert "Assumptions" not in content


def test_client_sections_do_not_repeat_review_label_in_page_header(tmp_path):
    ctx = _make_ctx()
    sections = [
        {"page": "snapshot", "markdown": "<div>cover</div>", "chapter_break": False},
        {"page": "methodology", "markdown": "<div>methodology</div>", "chapter_break": True},
    ]

    content = HTMLRenderer().render(sections, ctx, output_dir=tmp_path).read_text(
        encoding="utf-8"
    )

    assert "Cập nhật DHG - ĐANG XEM XÉT" not in content
    assert "Cập nhật DHG" in content
