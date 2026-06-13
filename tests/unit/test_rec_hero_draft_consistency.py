"""Regression: cover recommendation hero reads as a finished, official product.

The cover must not carry any draft/hedging note. The methodology page at the end
of the report explains how the figures are produced; the cover itself just shows
the conclusion (recommendation, target price, upside) cleanly.
"""
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


def test_cover_hero_has_no_warning_or_draft_note():
    html = _rec_hero(_vm("analyst_review_only"))

    assert "rec-draft-note" not in html
    assert "Dự thảo" not in html
    assert "chưa được công bố chính thức" not in html
    # The conclusion itself is still shown.
    assert "NẮM GIỮ" in html
    assert "91,476" in html


def test_cover_hero_clean_when_client_exportable():
    html = _rec_hero(_vm("client_exportable"))

    assert "rec-draft-note" not in html
    assert "NẮM GIỮ" in html
