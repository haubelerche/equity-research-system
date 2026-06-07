"""Tests for build_citations_appendix() and TableData.source_note."""
from __future__ import annotations

import pytest

from backend.reporting.section_builder import build_citations_appendix, _INTERNAL_TERMS
from backend.reporting.client_report_view_model import TableData


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sample_ledger() -> dict:
    """Minimal serialised ClaimLedger with two source_doc traces in different sections."""
    return {
        "ticker": "DBD",
        "report_id": "run_001",
        "claims": [
            {
                "claim_id": "abc123",
                "ticker": "DBD",
                "claim_type": "financial_fact",
                "claim_text": "Doanh thu 2025 đạt 1,865 tỷ VND",
                "numeric_value": 1865.0,
                "numeric_unit": "VND bn",
                "section": "financial_performance",
                "status": "supported",
                "traces": [
                    {
                        "trace_type": "source_doc",
                        "document_title": "BCTC hợp nhất 2025 sau kiểm toán",
                        "document_url": "https://bidiphar.com/bctc2025.pdf",
                    }
                ],
            },
            {
                "claim_id": "def456",
                "ticker": "DBD",
                "claim_type": "qualitative",
                "claim_text": "Kế hoạch AGM thông qua cổ tức 20%",
                "numeric_value": None,
                "numeric_unit": None,
                "section": "company_overview",
                "status": "supported",
                "traces": [
                    {
                        "trace_type": "source_doc",
                        "document_title": "Tài liệu ĐHĐCĐ 2026 Bidiphar",
                        "document_url": "https://bidiphar.com/agm2026.pdf",
                    }
                ],
            },
        ],
    }


# ---------------------------------------------------------------------------
# build_citations_appendix — output structure
# ---------------------------------------------------------------------------

class TestBuildCitationsAppendix:
    def test_returns_string(self):
        html = build_citations_appendix(_sample_ledger())
        assert isinstance(html, str)
        assert len(html) > 0

    def test_contains_section_heading(self):
        html = build_citations_appendix(_sample_ledger())
        assert "Nguồn" in html
        assert "Trích dẫn" in html

    def test_contains_source_titles(self):
        html = build_citations_appendix(_sample_ledger())
        assert "BCTC hợp nhất 2025 sau kiểm toán" in html
        assert "Tài liệu ĐHĐCĐ 2026 Bidiphar" in html

    def test_contains_hyperlinks(self):
        html = build_citations_appendix(_sample_ledger())
        assert "bidiphar.com" in html
        assert 'href="https://bidiphar.com/bctc2025.pdf"' in html

    def test_deduplicates_repeated_source(self):
        """Same document referenced from two claims should appear only once."""
        ledger = {
            "ticker": "DBD",
            "report_id": "run_002",
            "claims": [
                {
                    "claim_id": "a1",
                    "ticker": "DBD",
                    "claim_type": "financial_fact",
                    "claim_text": "Claim A",
                    "section": "valuation",
                    "status": "supported",
                    "traces": [{
                        "trace_type": "source_doc",
                        "document_title": "BCTC 2025",
                        "document_url": "https://example.com/bctc.pdf",
                    }],
                },
                {
                    "claim_id": "a2",
                    "ticker": "DBD",
                    "claim_type": "financial_fact",
                    "claim_text": "Claim B",
                    "section": "valuation",
                    "status": "supported",
                    "traces": [{
                        "trace_type": "source_doc",
                        "document_title": "BCTC 2025",
                        "document_url": "https://example.com/bctc.pdf",
                    }],
                },
            ],
        }
        html = build_citations_appendix(ledger)
        assert html.count("BCTC 2025") == 1

    def test_skips_non_source_doc_traces(self):
        """Fact/artifact/formula traces must not generate citation entries."""
        ledger = {
            "ticker": "DBD",
            "report_id": "run_003",
            "claims": [
                {
                    "claim_id": "b1",
                    "ticker": "DBD",
                    "claim_type": "valuation_output",
                    "claim_text": "Target price 30,000",
                    "section": "valuation",
                    "status": "supported",
                    "traces": [{
                        "trace_type": "artifact",
                        "artifact_path": "artifacts/blend.json",
                        "artifact_field": "target_price_vnd",
                    }],
                }
            ],
        }
        html = build_citations_appendix(ledger)
        assert html == ""

    def test_empty_ledger_returns_empty_string(self):
        assert build_citations_appendix({}) == ""
        assert build_citations_appendix({"claims": []}) == ""

    def test_none_ledger_returns_empty_string(self):
        assert build_citations_appendix(None) == ""  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# build_citations_appendix — cleanliness gate: no internal jargon
# ---------------------------------------------------------------------------

class TestCitationsAppendixCleanliness:
    """Appendix HTML must never expose internal audit terms."""

    def test_no_internal_terms_in_output(self):
        html = build_citations_appendix(_sample_ledger())
        lower = html.lower()
        for term in _INTERNAL_TERMS:
            assert term not in lower, (
                f"Internal term '{term}' found in citations appendix output"
            )

    def test_no_tier_in_output(self):
        html = build_citations_appendix(_sample_ledger())
        assert "tier" not in html.lower()

    def test_no_confidence_in_output(self):
        html = build_citations_appendix(_sample_ledger())
        assert "confidence" not in html.lower()

    def test_no_parser_in_output(self):
        html = build_citations_appendix(_sample_ledger())
        assert "parser" not in html.lower()

    def test_no_gate_in_output(self):
        html = build_citations_appendix(_sample_ledger())
        assert "gate" not in html.lower()

    def test_no_chunk_id_in_output(self):
        html = build_citations_appendix(_sample_ledger())
        assert "chunk_id" not in html.lower()


# ---------------------------------------------------------------------------
# TableData.source_note field
# ---------------------------------------------------------------------------

class TestTableDataSourceNote:
    def test_source_note_defaults_to_empty(self):
        table = TableData(
            title="Kết quả tài chính",
            periods=["2023", "2024", "2025"],
            rows=[("Doanh thu", [1600, 1750, 1865])],
            unit="tỷ VND",
        )
        assert table.source_note == ""

    def test_source_note_can_be_set(self):
        table = TableData(
            title="Kết quả tài chính",
            periods=["2023", "2024", "2025"],
            rows=[("Doanh thu", [1600, 1750, 1865])],
            unit="tỷ VND",
            source_note="Nguồn: BCTC kiểm toán 2025",
        )
        assert table.source_note == "Nguồn: BCTC kiểm toán 2025"

    def test_source_note_rendered_in_table_html(self):
        from backend.reporting.client_section_builder import _render_table
        table = TableData(
            title="Test Table",
            periods=["2025"],
            rows=[("Doanh thu", [1865])],
            unit="tỷ VND",
            source_note="Nguồn: BCTC kiểm toán 2025",
        )
        html = _render_table(table)
        assert "Nguồn: BCTC kiểm toán 2025" in html
        assert "table-source-note" in html

    def test_no_source_note_no_note_div(self):
        from backend.reporting.client_section_builder import _render_table
        table = TableData(
            title="Test Table",
            periods=["2025"],
            rows=[("Doanh thu", [1865])],
            unit="tỷ VND",
        )
        html = _render_table(table)
        assert "table-source-note" not in html
