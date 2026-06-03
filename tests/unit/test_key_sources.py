"""Tests for client-facing key sources rendering (Phase 08)."""
from __future__ import annotations

from backend.reporting.client_report_view_model import _clean_source_title, _key_sources


def test_clean_source_title_strips_tier_jargon():
    assert _clean_source_title("Balance Sheet (VCI) [Tier 3 — API tổng hợp]") == \
        "Bảng cân đối kế toán (dữ liệu thị trường VCI)"
    assert _clean_source_title("Income Statement (VCI) [Tier 3]") == \
        "Báo cáo kết quả kinh doanh (dữ liệu thị trường VCI)"
    assert _clean_source_title("Dữ liệu API tổng hợp [Tier 3]") == "Dữ liệu tài chính tổng hợp (VCI)"
    assert _clean_source_title("") is None


def test_key_sources_has_no_backend_jargon(monkeypatch):
    import backend.reporting.client_report_view_model as vm_mod
    monkeypatch.setattr(vm_mod, "_load_latest_citation", lambda t: {
        "citation_map": {
            "DBD/2022FY/x": {"source_title": "Balance Sheet (VCI) [Tier 3]", "fiscal_year": 2022},
            "DBD/2025FY/x": {"source_title": "Balance Sheet (VCI) [Tier 3]", "fiscal_year": 2025},
        }
    })

    class _Snap:
        as_of_date = "2026-06-03"

    sources = _key_sources("DBD", _Snap())
    assert sources, "key_sources must not be empty"
    joined = " ".join(s["label"] for s in sources)
    for jargon in ("Tier", "vnstock://", "artifact", "database"):
        assert jargon.lower() not in joined.lower()
    # financial statement source carries the fiscal-year span
    assert any("2022–2025" in s["label"] for s in sources)
    # internal valuation model is always listed
    assert any("FCFF/FCFE" in s["label"] for s in sources)
