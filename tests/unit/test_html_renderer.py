"""Unit tests for backend.reporting.html_renderer.HTMLRenderer."""
from __future__ import annotations

import pytest

from backend.reporting.section_builder import ReportContext, build_report_sections
from backend.reporting.html_renderer import HTMLRenderer


# ── Shared fixture ────────────────────────────────────────────────────────────

def _make_ctx() -> ReportContext:
    return ReportContext(
        ticker="DHG",
        company_name="Dược Hậu Giang",
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


# ── Tests ─────────────────────────────────────────────────────────────────────

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
    """There must be exactly 7 page-break divs (between each of 8 sections)."""
    ctx = _make_ctx()
    sections = build_report_sections(ctx)
    content = HTMLRenderer().render(sections, ctx, output_dir=tmp_path).read_text(encoding="utf-8")

    count = content.count('class="page-break"')
    assert count == 7, f"Expected 7 page-break divs, found {count}"


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
