"""Regression: cover recommendation hero reads as a finished, official product.

The cover must not carry any draft/hedging note. The methodology page at the end
of the report explains how the figures are produced; the cover itself just shows
the conclusion (recommendation, target price, upside) cleanly.
"""
from __future__ import annotations

from types import SimpleNamespace

from backend.reporting.client_section_builder import _rec_hero, _snapshot_page


def _vm(publication_status: str) -> SimpleNamespace:
    return SimpleNamespace(
        ticker="DHG",
        exchange="HOSE",
        recommendation="Giữ",
        target_price=SimpleNamespace(amount=91476.0),
        upside_downside=SimpleNamespace(value=-0.024),
        report_date="2026-06-12",
        publication_status=publication_status,
    )


def test_cover_hero_has_no_warning_or_draft_note():
    html = _rec_hero(_vm("analyst_review_only"))

    assert "rec-draft-note" not in html
    assert "Dự thảo" not in html
    assert "chưa được công bố chính thức" not in html
    # The conclusion itself is still shown.
    assert "Giữ" in html
    assert "91,476" in html


def test_cover_hero_clean_when_client_exportable():
    html = _rec_hero(_vm("client_exportable"))

    assert "rec-draft-note" not in html
    assert "Giữ" in html


def test_cover_hero_explains_missing_target_without_dash_vnd():
    vm = _vm("analyst_review_only")
    vm.target_price = None
    vm.upside_downside = None
    vm.display_blocking_reasons = ["no_eligible_valuation_method"]
    vm.missing_required_fields = ["target_price"]

    html = _rec_hero(vm)

    assert "Giá mục tiêu: <strong>—</strong>" in html
    assert "Tiềm năng tăng/giảm: <strong>—</strong>" in html
    assert "— VND" not in html
    assert "â€” VND" not in html


def test_snapshot_sidebar_keeps_computed_price_fields_visible():
    vm = _vm("analyst_review_only")
    vm.current_price = SimpleNamespace(amount=18_400.0)
    vm.total_return = SimpleNamespace(value=3.12)
    vm.market_price_as_of = "2026-05-13"
    vm.report_generated_at = "2026-06-17T10:51:00+07:00"
    vm.company_name = "MEDIPLANTEX"
    vm.sector = "Dược phẩm"
    vm.market_statistics = {
        "Mã giao dịch": "MED VN",
        "Giá đóng cửa": 18_400.0,
        "Vốn hóa": 228.0,
        "Số lượng cổ phiếu": 12.4,
    }
    vm.charts = {}
    vm.investment_thesis = "Luận điểm định giá có số liệu."
    vm.latest_business_update = "Cập nhật hoạt động."
    vm.key_growth_drivers = "Động lực tăng trưởng."
    vm.news_citations = []

    html = _snapshot_page(vm)

    assert "91,476 VND" in html
    assert "18,400" in html
    assert "Giá mục tiêu: <strong>—</strong>" not in html
