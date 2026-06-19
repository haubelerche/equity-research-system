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
        lambda vm: "<div>Phương pháp định giá và nguồn dữ liệu</div>",
    )

    sections = csb.build_client_report_sections(SimpleNamespace())

    assert sections[-1]["page"] == "report_status"
    assert sections[-1]["title"] == "Phương pháp định giá và nguồn dữ liệu"
    assert sections[-1]["chapter_break"] is False
    # Sections now flow naturally; forced chapter breaks created sparse PDF pages.
    assert all(section["chapter_break"] is False for section in sections)
    assert all(
        "Phương pháp định giá và nguồn dữ liệu" not in section["markdown"]
        for section in sections[:-1]
    )


def test_methodology_page_explains_data_calculation_and_decision_without_warnings():
    vm = SimpleNamespace(
        recommendation="Giữ",
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
        report_generated_at="2026-06-16T10:15:00+07:00",
        market_price_as_of="2026-06-16",
        valuation_evidence={
            "formula_trace_count": 5,
            "formula_trace_methods": ["fcff", "blend_dcf"],
            "peer_data_source": "VN pharma peers: IMP, DMC, TRA",
            "relative_valuation_status": "peer_data_available",
            "market_sanity_bridge": {"target_to_market": 1.139, "bridge_present": True},
            "display_blocking_reasons": ["blend_is_draft_only"],
            "policy_blocking_reasons": ["market_sanity_bridge_missing"],
            "model_warnings": [
                "FCFE BLOCKED - debt schedule unavailable",
                "target_pe=15.0x is model default — validate with peer-median P/E before publishing",
                "Relative valuation is PENDING — no peer_data_source provided.",
            ],
            "market_data_warnings": ["served from cache; live fetch failed"],
        },
    )

    html = csb._report_status_page(vm)

    assert "Phương pháp định giá và nguồn dữ liệu" in html
    # Explains where the quantitative numbers come from and how they are computed.
    assert "Báo cáo tài chính" in html
    assert "FCFF/FCFE" in html
    assert "WACC" in html or "chi phí vốn bình quân" in html
    # Decision rule + the actual conclusion are stated.
    assert "Mua nếu &gt;20%, Bán nếu &lt;-10%, còn lại là Giữ" in html
    assert "khuyến nghị: Giữ" in html
    assert "2026-06-16" in html
    assert "2026-06-16 10:15:00+07:00" in html
    # Citation legend: real, always-present sources are numbered.
    assert "<strong>[1]</strong>" in html
    assert "<strong>[2]</strong>" in html
    assert "Số vết công thức" in html
    assert "VN pharma peers: IMP, DMC, TRA" in html
    assert "Dữ liệu thị trường đang dùng bản đã lưu gần nhất" not in html
    assert "market_sanity_bridge_missing" not in html
    assert "blend_is_draft_only" not in html
    assert "target_pe=15.0x is model default" not in html
    assert "Relative valuation is PENDING" not in html
    assert "Giá trị mô hình lệch đáng kể so với thị giá" not in html
    assert "P/E mục tiêu đang là giả định mặc định" not in html
    assert "Định giá tương đối thiếu bộ doanh nghiệp so sánh" not in html
    assert "Dữ liệu và kiểm định cần bổ sung trước khi phát hành" not in html
    assert "Cảnh báo mô hình và dữ liệu" not in html
    assert "Cần rà soát thêm một cảnh báo dữ liệu hoặc phương pháp" not in html
    assert "thuộc về người đọc" not in html
    # The hedging "sensitive points to check" warning list is gone.
    assert "Các điểm nhạy cảm" not in html
    # No internal jargon / leaked artifacts.
    assert "backend/news" not in html
    assert "recommendation_gate_not_allowed" not in html
    assert "valuation_result_not_publishable" not in html
    assert "peer_data_source" not in html
    assert "BLOCKED" not in html
    assert "blocked" not in html
    assert "bị chặn" not in html
    assert "Cảnh báo chặn phát hành" not in html
    assert "chưa công bố chính thức" not in html.lower()
    assert "English reviewer note" not in html


def test_methodology_page_explains_missing_target_price_without_dash_vnd():
    vm = SimpleNamespace(
        current_price=SimpleNamespace(amount=12_300),
        target_price=None,
        upside_downside=None,
        total_return=None,
        display_blocking_reasons=["no_eligible_valuation_method"],
        missing_required_fields=["target_price"],
        key_sources=[],
        news_citations=[],
        disclaimer="Báo cáo này chỉ nhằm mục đích cung cấp thông tin.",
        critic_findings=[],
        report_generated_at="2026-06-18T10:15:00+07:00",
        market_price_as_of="2026-06-18",
        valuation_evidence={"display_blocking_reasons": ["no_eligible_valuation_method"]},
    )

    html = csb._report_status_page(vm)

    assert "giá mục tiêu chưa được công bố" in html
    assert "Thiếu phương pháp định giá chính" in html
    assert "— VND" not in html
    assert "â€” VND" not in html


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
