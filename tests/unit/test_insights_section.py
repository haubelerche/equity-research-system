"""The report renders ready insights with their evidence markers; skips insufficient ones."""
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


def test_renders_ready_insight_with_evidence_and_implication():
    html = csb._insights_page(_vm())
    assert "Phân tích" in html
    assert "Lợi nhuận tăng nhanh hơn doanh thu nhờ cải thiện biên." in html
    assert "[1][2]" in html
    assert "Hàm ý định giá" in html
    assert "Không nên nâng tăng trưởng dài hạn." in html


def test_skips_insufficient_evidence_insight():
    html = csb._insights_page(_vm())
    assert "Chưa đủ dữ liệu biên." not in html


def test_empty_pack_renders_no_section_body():
    html = csb._insights_page(SimpleNamespace(insight_pack=[]))
    # No insight items, but must not crash and must not assert false content.
    assert "Hàm ý định giá" not in html
