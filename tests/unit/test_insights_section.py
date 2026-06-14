"""Insights render as prose in relevant report sections."""
from __future__ import annotations

from types import SimpleNamespace

from backend.reporting import client_section_builder as csb


def _vm():
    return SimpleNamespace(
        insight_pack=[
            {
                "section": "growth",
                "claim": "Lợi nhuận tăng nhanh hơn doanh thu nhờ cải thiện biên.",
                "evidence_refs": ["[1]", "[2]"],
                "analysis_logic": "So sánh tăng trưởng lợi nhuận với doanh thu.",
                "valuation_implication": "Không nên nâng tăng trưởng dài hạn.",
                "status": "ready",
                "missing_fields": [],
            },
            {
                "section": "margin",
                "claim": "Chưa đủ dữ liệu biên.",
                "evidence_refs": ["[1]"],
                "analysis_logic": "x",
                "valuation_implication": "",
                "status": "insufficient_evidence",
                "missing_fields": ["gross_margin_latest"],
            },
        ]
    )


def test_renders_ready_insight_as_section_prose_with_evidence_and_implication():
    html = csb._render_section_insights(_vm(), {"growth"})
    assert "Nhận định:" in html
    assert "Lợi nhuận tăng nhanh hơn doanh thu nhờ cải thiện biên." in html
    assert "[1][2]" in html
    assert "Không nên nâng tăng trưởng dài hạn." in html
    assert "So sánh tăng trưởng lợi nhuận với doanh thu." not in html


def test_filters_by_section_and_skips_insufficient_evidence_insight():
    html = csb._render_section_insights(_vm(), {"margin"})
    assert "Lợi nhuận tăng nhanh hơn doanh thu nhờ cải thiện biên." not in html
    assert "Chưa đủ dữ liệu biên." not in html


def test_empty_pack_renders_no_section_body():
    assert csb._render_section_insights(SimpleNamespace(insight_pack=[]), {"growth"}) == ""


def test_client_report_has_no_standalone_insights_chapter(monkeypatch):
    monkeypatch.setattr(csb, "_snapshot_page", lambda vm: "<div>snapshot</div>")
    monkeypatch.setattr(csb, "_business_financials_page", lambda vm: "<div>business</div>")
    monkeypatch.setattr(csb, "_valuation_page", lambda vm: "<div>valuation</div>")
    monkeypatch.setattr(csb, "_risks_sources_page", lambda vm: "<div>risks</div>")
    monkeypatch.setattr(csb, "_appendix_page", lambda vm: "<div>appendix</div>")
    monkeypatch.setattr(csb, "_report_status_page", lambda vm: "<div>status</div>")

    sections = csb.build_client_report_sections(SimpleNamespace())

    assert "insights" not in {section["page"] for section in sections}
    assert "Phân tích và nhận định" not in {section["title"] for section in sections}
