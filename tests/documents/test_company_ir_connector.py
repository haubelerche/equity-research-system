"""Phase 3A — company IR discovery connector (offline, injected HTML)."""
from __future__ import annotations

from backend.documents.company_registry import get_company
from backend.documents.connectors.base import infer_document_type, infer_fiscal_year
from backend.documents.connectors.company_ir_connector import CompanyIRConnector

# Real DHG IR link patterns (from dhgpharma.com.vn) used as a fixture.
_FIXTURE_HTML = """
<html><body>
<a href="/sites/default/files/2026-03/DHG-Audited-FS-2025-VN.pdf">BCTC kiểm toán 2025</a>
<a href="/sites/default/files/2025-04/1.%20Bao-cao-thuong-nien-2024.pdf">BCTN 2024</a>
<a href="/sites/default/files/2024-08/Bao-cao-thuong-nien-2022.pdf">BCTN 2022</a>
<a href="/sites/default/files/2026-04/DHG-BCTC-Q1.2026.pdf">BCTC Q1 2026</a>
<a href="/sites/default/files/2026-01/VN-DHG-BCTC-Q4.2025.pdf">BCTC Q4 2025</a>
<a href="/vi/some-page">not a file</a>
</body></html>
"""


def _stub_get(url: str) -> str:
    return _FIXTURE_HTML


def test_ir_connector_parses_candidates():
    company = get_company("DHG")
    conn = CompanyIRConnector()
    cands = conn.discover(company, 2021, 2025, http_get=_stub_get)
    # Q1.2026 is out of range → excluded; the rest within 2021-2025 remain.
    years_types = {(c.fiscal_year, c.document_type) for c in cands}
    assert (2025, "audited_financial_statement") in years_types
    assert (2024, "annual_report") in years_types
    assert (2022, "annual_report") in years_types
    assert (2025, "financial_statement") in years_types   # Q4.2025
    # All from company_ir with absolute URLs and >0 confidence
    for c in cands:
        assert c.source_name == "company_ir"
        assert c.source_url.startswith("https://dhgpharma.com.vn/")
        assert 0 < c.confidence <= 1
        assert c.fiscal_year is not None


def test_ir_connector_respects_year_range():
    company = get_company("DHG")
    cands = CompanyIRConnector().discover(company, 2021, 2024, http_get=_stub_get)
    assert all(c.fiscal_year <= 2024 for c in cands)
    assert all(c.fiscal_year >= 2021 for c in cands)


def test_infer_helpers():
    assert infer_fiscal_year("DHG-Audited-FS-2025-VN.pdf") == 2025
    assert infer_fiscal_year("VN-DHG-BCTC-Q4.2025.pdf") == 2025
    assert infer_fiscal_year("no-year-here.pdf") is None
    assert infer_document_type("Bao-cao-thuong-nien-2024.pdf")[0] == "annual_report"
    assert infer_document_type("DHG-Audited-FS-2025-VN.pdf")[0] == "audited_financial_statement"
    assert infer_document_type("DHG-CBTT-giai-trinh-2025.pdf")[0] == "disclosure"
