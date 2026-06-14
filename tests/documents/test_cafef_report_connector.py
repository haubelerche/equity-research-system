"""Offline tests for the CafeF FinanceReport.ashx evidence connector.

Uses captured JSON fixtures (tests/fixtures/cafef/) so the connector is testable
without network. The connector turns CafeF's machine-readable audited-statement
endpoint into accountable evidence records (api_url + audited flag) for ingestion.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.documents.connectors.cafef_report_connector import (
    CafeFReportConnector,
    CafeFReportEvidence,
)

_FIX = Path(__file__).resolve().parents[1] / "fixtures" / "cafef"


def _fixture_http_get():
    """Return an http_get that serves captured fixtures keyed by Type=N in the URL."""
    type_to_file = {
        "Type=1": _FIX / "DBD_type1_income_statement.json",
        "Type=2": _FIX / "DBD_type2_balance_sheet.json",
    }

    def http_get(url: str) -> str:
        for token, path in type_to_file.items():
            if token in url:
                return path.read_text(encoding="utf-8")
        # Unknown type (e.g. cash flow Type=3) -> empty CafeF payload
        return json.dumps({"Data": {"Count": 0, "Value": []}, "Success": True, "Message": None})

    return http_get


def test_fetch_evidence_returns_per_year_statement_records():
    conn = CafeFReportConnector()
    evidence = conn.fetch_evidence("DBD", 2022, 2025, http_get=_fixture_http_get())

    # IS + BS across 4 fiscal years = 8 records.
    assert len(evidence) == 8
    assert {e.statement_type for e in evidence} == {"income_statement", "balance_sheet"}
    assert {e.fiscal_year for e in evidence} == {2022, 2023, 2024, 2025}
    assert all(isinstance(e, CafeFReportEvidence) for e in evidence)


def test_year_range_filter_excludes_out_of_range_years():
    conn = CafeFReportConnector()
    evidence = conn.fetch_evidence("DBD", 2024, 2025, http_get=_fixture_http_get())
    assert {e.fiscal_year for e in evidence} == {2024, 2025}


def test_evidence_carries_accountable_provenance():
    conn = CafeFReportConnector()
    evidence = conn.fetch_evidence("DBD", 2025, 2025, http_get=_fixture_http_get())
    is_2025 = next(e for e in evidence if e.statement_type == "income_statement")
    # Provenance: exact endpoint URL + audited flag from CafeF "Conten".
    assert "FinanceReport.ashx" in is_2025.api_url
    assert "Type=1" in is_2025.api_url and "Symbol=DBD" in is_2025.api_url
    assert is_2025.audited is True
    assert is_2025.source_tier == 2


def test_line_items_parsed_with_values_and_ty_conversion():
    conn = CafeFReportConnector()
    evidence = conn.fetch_evidence("DBD", 2025, 2025, http_get=_fixture_http_get())
    is_2025 = next(e for e in evidence if e.statement_type == "income_statement")
    by_code = {li["code"]: li for li in is_2025.line_items}
    # Raw value preserved (thousand VND) + tỷ-đồng conversion (value / 1e6).
    assert by_code["DTTBHCCDV"]["value_thousand_vnd"] == 1946612660
    assert round(by_code["DTTBHCCDV"]["value_ty_dong"], 1) == 1946.6
    assert by_code["NetIncome"]["name"]  # Vietnamese label retained


def test_evidence_text_is_human_readable_and_grounded():
    conn = CafeFReportConnector()
    evidence = conn.fetch_evidence("DBD", 2025, 2025, http_get=_fixture_http_get())
    is_2025 = next(e for e in evidence if e.statement_type == "income_statement")
    text = is_2025.evidence_text
    assert "DBD" in text and "2025" in text
    assert "Đã kiểm toán" in text
    assert "Doanh thu" in text
    # A retrievable, grounded number must appear.
    assert "1.946" in text or "1946" in text


def test_empty_statement_yields_no_records():
    conn = CafeFReportConnector()
    # Cash flow (Type=3) returns empty -> no fabricated records.
    out = conn.fetch_statement("DBD", 3, 2025, http_get=_fixture_http_get())
    assert out == []
