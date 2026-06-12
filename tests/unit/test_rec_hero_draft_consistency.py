"""Regression: cover rec hero must signal draft when report is not publication-ready,
so it agrees with the running header and the status page (no published-vs-draft contradiction)."""
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


def test_draft_note_present_when_not_exportable():
    html = _rec_hero(_vm("analyst_review_only"))
    assert "rec-draft-note" in html
    assert "Dự thảo" in html


def test_no_draft_note_when_client_exportable():
    html = _rec_hero(_vm("client_exportable"))
    assert "rec-draft-note" not in html
