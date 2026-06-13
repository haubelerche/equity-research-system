"""Regression tests for generic source notes in client-facing reports."""
from __future__ import annotations

from backend.reporting.layout_audit import run_layout_audit
from backend.reporting.report_artifact import ReportArtifact, SECTION_IDS, make_section


def _long_section(section_id: str, suffix: str) -> str:
    return (
        f"<section><h2>{section_id}</h2>"
        f"<p>Phần này dùng để kiểm tra chất lượng trình bày báo cáo khách hàng. "
        f"Nội dung mô tả bối cảnh, số liệu, giả định, kết quả phân tích, rủi ro, "
        f"khả năng kiểm chứng và yêu cầu truy vết nguồn dữ liệu cho từng bảng. "
        f"Đoạn văn có nội dung riêng cho mục {suffix} để tránh bị nhận diện là "
        f"sao chép giữa các phần trong báo cáo.</p></section>"
    )


def test_client_final_fails_when_generic_source_note_is_present() -> None:
    sections = []
    for i, section_id in enumerate(SECTION_IDS):
        html = _long_section(section_id, f"mã {i}")
        if section_id == "valuation_model":
            html += "<p>Nguồn nhóm phân tích thu thập.</p>"
        sections.append(make_section(section_id, section_id, html))
    artifact = ReportArtifact(
        report_id="test_generic_source",
        ticker="DHG",
        run_id="run_test",
        report_date="2026-06-13",
        render_mode="client_final",
        sections=sections,
    )

    audit = run_layout_audit(artifact)

    assert audit.layout_gate_status == "FAIL"
    assert any(issue.check_name == "generic_source_note" for issue in audit.errors)
