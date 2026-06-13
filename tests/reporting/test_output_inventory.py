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


def test_output_dir_does_not_exist(tmp_path: Path):
    """When output_dir is absent entirely, every item reports has_report=False with no exception."""
    missing = tmp_path / "nonexistent_dir"
    items = scan_report_inventory(missing, _universe())
    assert len(items) == 2
    for item in items:
        assert item.has_report is False
        assert item.preview_pages == []
        assert item.report_size is None
        assert item.updated_at is None


def test_preview_dir_absent_yields_empty_pages(tmp_path: Path):
    """Ticker has a report PDF but no pdf_preview/ subdirectory → preview_pages is []."""
    out = tmp_path
    (out / "DHG_report.pdf").write_bytes(b"%PDF-1.4 report")
    # No pdf_preview directory created

    items = scan_report_inventory(out, [_universe()[0]])

    dhg = items[0]
    assert dhg.has_report is True
    assert dhg.preview_pages == []


def test_lowercase_ticker_in_universe_resolves_uppercase_files(tmp_path: Path):
    """A lowercase ticker in the universe row still resolves DHG_*.pdf (resolver uppercases it)."""
    out = tmp_path
    (out / "DHG_report.pdf").write_bytes(b"%PDF-1.4 report")
    preview = out / "pdf_preview"
    preview.mkdir()
    (preview / "DHG_report_page_1.png").write_bytes(b"png")

    universe_lower = [
        {"ticker": "dhg", "company_name": "Duoc Hau Giang", "exchange": "HOSE", "segment": "pharma", "is_mvp": True}
    ]
    items = scan_report_inventory(out, universe_lower)

    dhg = items[0]
    assert dhg.ticker == "DHG"
    assert dhg.has_report is True
    assert dhg.preview_pages == [1]


def test_directory_inside_preview_not_counted_as_page(tmp_path: Path):
    """A subdirectory named like a valid preview file must NOT be counted as a page."""
    out = tmp_path
    (out / "DHG_report.pdf").write_bytes(b"%PDF-1.4 report")
    preview = out / "pdf_preview"
    preview.mkdir()
    # Real file page
    (preview / "DHG_report_page_1.png").write_bytes(b"png")
    # Directory that looks like a valid preview file — must be skipped
    (preview / "DHG_report_page_9.png").mkdir()

    items = scan_report_inventory(out, [_universe()[0]])

    dhg = items[0]
    assert dhg.preview_pages == [1]  # page 9 (directory) must NOT be counted
