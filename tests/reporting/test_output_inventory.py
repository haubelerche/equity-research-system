from pathlib import Path
from backend.reporting.output_inventory import scan_report_inventory, ReportInventoryItem


def _universe():
    return [
        {"ticker": "DHG", "company_name": "Duoc Hau Giang", "exchange": "HOSE", "segment": "pharma", "is_mvp": True},
        {"ticker": "IMP", "company_name": "Imexpharm", "exchange": "HOSE", "segment": "pharma", "is_mvp": True},
    ]


def test_scan_reports_present_and_absent(tmp_path: Path):
    out = tmp_path
    (out / "DHG_report.pdf").write_bytes(b"%PDF-1.4 report")
    (out / "DHG_explanation.pdf").write_bytes(b"%PDF-1.4 expl")
    preview = out / "pdf_preview"
    preview.mkdir()
    # intentionally out of lexicographic order to prove numeric sort
    for p in [1, 2, 12, 4, 3]:
        (preview / f"DHG_report_page_{p}.png").write_bytes(b"png")

    items = scan_report_inventory(out, _universe())

    assert [i.ticker for i in items] == ["DHG", "IMP"]  # aligned to universe order
    dhg = items[0]
    assert isinstance(dhg, ReportInventoryItem)
    assert dhg.has_report is True
    assert dhg.has_explanation is True
    assert dhg.preview_pages == [1, 2, 3, 4, 12]  # numeric sort, not string
    assert dhg.report_size > 0
    assert dhg.updated_at is not None

    imp = items[1]
    assert imp.has_report is False
    assert imp.has_explanation is False
    assert imp.preview_pages == []
    assert imp.report_size is None
    assert imp.updated_at is None
