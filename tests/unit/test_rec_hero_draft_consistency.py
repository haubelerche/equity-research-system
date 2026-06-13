"""Regression: cover recommendation hero points readers to the methodology page."""
from __future__ import annotations

from types import SimpleNamespace

from backend.reporting.client_section_builder import _rec_hero


def _vm(publication_status: str) -> SimpleNamespace:
    return SimpleNamespace(
        ticker="DHG",
        exchange="HOSE",
        recommendation="NẮM GIỮ",
        target_price=SimpleNamespace(amount=91476.0),
        upside_downside=SimpleNamespace(value=-0.024),
        report_date="2026-06-12",
        publication_status=publication_status,
    )


def test_methodology_note_present_without_draft_warning():
    html = _rec_hero(_vm("analyst_review_only"))

    assert "rec-draft-note" in html
    assert "mô hình định lượng" in html
    assert "giải trình phương pháp" in html
    assert "Dự thảo" not in html
    assert "chưa được công bố chính thức" not in html


def test_methodology_note_also_present_when_client_exportable():
    html = _rec_hero(_vm("client_exportable"))

    assert "rec-draft-note" in html
    assert "giải trình phương pháp" in html
