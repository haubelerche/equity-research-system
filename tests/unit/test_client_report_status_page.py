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
    # Every section after the cover emits an inline page-header ("Cập nhật DHG /
    # Ngày ...") at its top. Each such section must therefore start on a fresh
    # page; otherwise the header floats into the middle of a flowing page.
    assert all(section["chapter_break"] is True for section in sections[1:])
    assert all(
        "Giải trình phương pháp và quyết định" not in section["markdown"]
        for section in sections[:-1]
    )


def test_methodology_page_explains_data_calculation_and_decision_without_warnings():
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
        news_citations=[],
        disclaimer="Báo cáo này chỉ nhằm mục đích cung cấp thông tin.",
        critic_findings=["English reviewer note must not be copied into the client page."],
    )

    html = csb._report_status_page(vm)

    assert "Giải trình phương pháp và quyết định" in html
    # Explains where the quantitative numbers come from and how they are computed.
    assert "Báo cáo tài chính" in html
    assert "FCFF/FCFE" in html
    assert "WACC" in html or "chi phí vốn bình quân" in html
    # Decision rule + the actual conclusion are stated.
    assert "MUA nếu &gt;20%, BÁN nếu &lt;-10%, còn lại là NẮM GIỮ" in html
    assert "khuyến nghị hệ thống: NẮM GIỮ" in html
    # Citation legend: real, always-present sources are numbered.
    assert "<strong>[1]</strong>" in html
    assert "<strong>[2]</strong>" in html
    # Responsibility shifts to the reader, who can verify every assumption.
    assert "thuộc về người đọc" in html
    # The hedging "sensitive points to check" warning list is gone.
    assert "Các điểm nhạy cảm" not in html
    # No internal jargon / leaked artifacts.
    assert "backend/news" not in html
    assert "chưa công bố chính thức" not in html.lower()
    assert "English reviewer note" not in html


def test_low_news_coverage_note_when_no_articles():
    vm = SimpleNamespace(key_sources=[], news_citations=[])
    html = csb._render_methodology_sources(vm)
    assert "<strong>[1]</strong>" in html
    assert "hạn chế về coverage nguồn tin" in html
    assert "[3]" not in html  # no fabricated news reference


def test_real_news_article_is_listed_and_linked_when_present():
    vm = SimpleNamespace(
        key_sources=[],
        news_citations=[
            {
                "source_name": "Tin nhanh Chứng khoán",
                "title": "DHG quý I/2026 hoàn thành 34,5% kế hoạch lợi nhuận năm",
                "url": "https://www.tinnhanhchungkhoan.vn/dhg-q1-post389927.html",
                "published_at": "2026-05-05",
            }
        ],
    )
    html = csb._render_methodology_sources(vm)
    assert "<strong>[3]</strong>" in html
    assert "Tin nhanh Chứng khoán" in html
    assert 'href="https://www.tinnhanhchungkhoan.vn/dhg-q1-post389927.html"' in html
    assert "hạn chế về coverage nguồn tin" not in html  # not low-coverage when we have news


def test_qualitative_assertions_receive_source_markers():
    assert csb._with_refs("Doanh thu tăng nhờ kênh bán hàng mở rộng.", "[1]").endswith("[1]")
    assert csb._with_refs("Luận điểm đã có nguồn. [1]", "[1]").endswith("[1]")
