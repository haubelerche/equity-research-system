"""Unit tests for backend.reporting.html_renderer.HTMLRenderer."""
from __future__ import annotations

from backend.reporting.html_renderer import HTMLRenderer
from backend.reporting.section_builder import ReportContext, build_report_sections


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


def test_html_renderer_creates_html_file(tmp_path):
    ctx = _make_ctx()
    sections = build_report_sections(ctx)
    out = HTMLRenderer().render(sections, ctx, output_dir=tmp_path)

    assert out.exists()
    assert out.suffix == ".html"

    content = out.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in content
    assert "DHG" in content


def test_html_contains_disclaimer(tmp_path):
    ctx = _make_ctx()
    sections = build_report_sections(ctx)
    content = HTMLRenderer().render(sections, ctx, output_dir=tmp_path).read_text(encoding="utf-8")

    assert "khuyến nghị đầu tư cá nhân hóa" in content


def test_html_has_8_sections(tmp_path):
    ctx = _make_ctx()
    sections = build_report_sections(ctx)
    content = HTMLRenderer().render(sections, ctx, output_dir=tmp_path).read_text(encoding="utf-8")

    assert content.count('class="report-section"') == 8


def test_html_has_page_breaks(tmp_path):
    ctx = _make_ctx()
    sections = build_report_sections(ctx)
    content = HTMLRenderer().render(sections, ctx, output_dir=tmp_path).read_text(encoding="utf-8")

    assert content.count('class="page-break"') == 0


def test_output_filename_with_run_id(tmp_path):
    ctx = _make_ctx()
    sections = build_report_sections(ctx)
    out = HTMLRenderer().render(sections, ctx, output_dir=tmp_path, run_id="RUN_001")

    assert out.name.startswith("RUN_001_DHG")


def test_output_filename_without_run_id(tmp_path):
    ctx = _make_ctx()
    sections = build_report_sections(ctx)
    out = HTMLRenderer().render(sections, ctx, output_dir=tmp_path, run_id="")

    assert out.name == "DHG_report.html"


def test_html_is_valid_utf8(tmp_path):
    ctx = _make_ctx()
    sections = build_report_sections(ctx)
    out = HTMLRenderer().render(sections, ctx, output_dir=tmp_path)

    assert out.read_text(encoding="utf-8")


def test_output_dir_created_if_missing(tmp_path):
    nested = tmp_path / "deep" / "nested" / "dir"
    assert not nested.exists()

    ctx = _make_ctx()
    sections = build_report_sections(ctx)
    out = HTMLRenderer().render(sections, ctx, output_dir=nested)

    assert nested.exists()
    assert out.exists()


def test_client_final_mode_hides_internal_status_banner(tmp_path):
    ctx = _make_ctx()
    sections = build_report_sections(ctx)
    content = HTMLRenderer().render(
        sections, ctx, output_dir=tmp_path, render_mode="client_final"
    ).read_text(encoding="utf-8")

    assert '<div class="draft-banner">' not in content
    assert "BÁO CÁO NHÁP (DRAFT)" not in content
    assert "NEEDS_REVIEW" not in content


def test_default_mode_does_not_render_internal_status_banner(tmp_path):
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


def test_html_renderer_repairs_template_mojibake(tmp_path):
    ctx = _make_ctx()
    sections = [
        {
            "page": "snapshot",
            "markdown": "GiÃ¡ má»¥c tiÃªu hiá»‡n táº¡i â€” cáº§n rÃ  soÃ¡t.",
            "chapter_break": False,
        }
    ]

    content = HTMLRenderer().render(sections, ctx, output_dir=tmp_path).read_text(
        encoding="utf-8"
    )

    assert "Giá mục tiêu hiện tại — cần rà soát." in content
    assert "Báo cáo nghiên cứu cổ phiếu" in content
    assert "BÃ¡o" not in content
    assert "GiÃ¡" not in content
    assert "â€”" not in content
