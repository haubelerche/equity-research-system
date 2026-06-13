"""Regression tests for the final client-facing methodology page."""
from __future__ import annotations

from types import SimpleNamespace

from backend.reporting import client_section_builder as csb


def test_methodology_page_is_the_final_client_section(monkeypatch):
    monkeypatch.setattr(csb, "_snapshot_page", lambda vm: "<div>snapshot</div>")
    monkeypatch.setattr(csb, "_business_financials_page", lambda vm: "<div>business</div>")
    monkeypatch.setattr(csb, "_valuation_page", lambda vm: "<div>valuation</div>")
    monkeypatch.setattr(csb, "_risks_sources_page", lambda vm: "<div>risks</div>")
    monkeypatch.setattr(csb, "_appendix_page", lambda vm: "<div>appendix</div>")
    monkeypatch.setattr(
        csb,
        "_report_status_page",
        lambda vm: "<div>Giải trình phương pháp và quyết định</div>",
    )

    sections = csb.build_client_report_sections(SimpleNamespace())

    assert sections[-1]["page"] == "report_status"
    assert sections[-1]["title"] == "Giải trình phương pháp và quyết định"
    assert sections[-1]["chapter_break"] is True
    assert all(
        "Giải trình phương pháp và quyết định" not in section["markdown"]
        for section in sections[:-1]
    )


def test_methodology_page_explains_data_news_calculation_and_decision():
    vm = SimpleNamespace(
        recommendation="NẮM GIỮ",
        publication_status="analyst_review_only",
        current_price=SimpleNamespace(amount=93_700),
        target_price=SimpleNamespace(amount=106_752),
        upside_downside=SimpleNamespace(value=0.139),
        total_return=SimpleNamespace(value=0.139),
        display_blocking_reasons=["valuation_gap_gt_25pct"],
        missing_required_fields=["approval_status"],
        key_sources=[{"label": "Báo cáo tài chính công ty"}],
        disclaimer="Báo cáo này chỉ nhằm mục đích cung cấp thông tin.",
        critic_findings=["English reviewer note must not be copied into the client page."],
    )

    html = csb._report_status_page(vm)

    assert "Giải trình phương pháp và quyết định" in html
    assert "tin tức không được dùng làm nguồn số liệu định lượng trực tiếp" in html
    assert "Mô-đun tin tức" in html
    assert "backend/news" not in html
    assert "VnExpress, VnEconomy, CafeF và Vietstock" in html
    assert "FCFF/FCFE" in html
    assert "<strong>[1]</strong> Dữ liệu tài chính công ty" in html
    assert "<strong>[2]</strong> Mô hình định giá nội bộ" in html
    assert "<strong>[3]</strong> Mô-đun tin tức" in html
    assert "MUA nếu &gt;20%, BÁN nếu &lt;-10%, còn lại là NẮM GIỮ" in html
    assert "khuyến nghị hệ thống: NẮM GIỮ" in html
    assert "chưa công bố chính thức" not in html.lower()
    assert "English reviewer note" not in html


def test_qualitative_assertions_receive_source_markers():
    assert csb._with_refs("Doanh thu tăng nhờ kênh bán hàng mở rộng.", "[1][3]").endswith("[1][3]")
    assert csb._with_refs("Luận điểm đã có nguồn. [1]", "[1][3]").endswith("[1]")
