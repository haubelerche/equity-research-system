from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from backend.api import create_app


@pytest.fixture(autouse=True)
def _disable_export_storage(monkeypatch):
    def _raise_unconfigured():
        raise ValueError("storage disabled in report endpoint tests")

    monkeypatch.setattr("backend.storage.SupabaseStorageAdapter", _raise_unconfigured)


def _make_client(tmp_path: Path, *, with_local_files: bool = True) -> TestClient:
    out = tmp_path / "output"
    out.mkdir()
    if with_local_files:
        (out / "DHG_report.pdf").write_bytes(b"%PDF-1.4 report")
        (out / "DHG_explanation.pdf").write_bytes(b"%PDF-1.4 expl")
        pv = out / "pdf_preview"
        pv.mkdir()
        (pv / "DHG_report_page_1.png").write_bytes(b"png")

    csv = tmp_path / "universe.csv"
    csv.write_text(
        "ticker,company_name,exchange,segment,is_mvp,notes\n"
        "DHG,Duoc Hau Giang,HOSE,pharma,true,MVP core\n"
        "IMP,Imexpharm,HOSE,pharma,true,MVP core\n",
        encoding="utf-8",
    )
    app = create_app(check_schema_on_startup=False)
    app.state.report_output_dir = out
    app.state.report_universe_csv = csv
    return TestClient(app)


def test_get_reports_lists_universe_with_status(tmp_path):
    client = _make_client(tmp_path)
    resp = client.get("/reports")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert [i["ticker"] for i in items] == ["DHG", "IMP"]
    assert items[0]["has_report"] is True
    assert items[0]["has_explanation"] is True
    assert items[0]["preview_pages"] == [1]
    assert isinstance(items[0]["renderable_run_ids"], list)
    assert items[0]["lineage_source"] in {"manifest", "local_files"}
    assert items[1]["has_report"] is False


def test_get_report_file_ok_and_404(tmp_path):
    client = _make_client(tmp_path)

    ok = client.get("/reports/DHG/file/report")
    assert ok.status_code == 200
    assert ok.headers["content-type"] == "application/pdf"
    assert ok.headers["cache-control"] == "no-store"
    assert ok.content.startswith(b"%PDF")

    missing = client.get("/reports/IMP/file/report")  # IMP has no file
    assert missing.status_code == 404


def test_get_report_file_rejects_unknown_ticker_and_bad_kind(tmp_path):
    client = _make_client(tmp_path)
    assert client.get("/reports/ZZZ/file/report").status_code == 404  # not in universe
    assert client.get("/reports/DHG/file/secrets").status_code == 404  # bad kind
    # path traversal attempt in ticker must not escape output dir
    assert client.get("/reports/..%2f..%2fetc/file/report").status_code == 404


def test_get_preview_png_ok_and_404(tmp_path):
    client = _make_client(tmp_path)
    ok = client.get("/reports/DHG/preview/1")
    assert ok.status_code == 200
    assert ok.headers["content-type"] == "image/png"
    assert ok.headers["cache-control"] == "no-store"
    assert client.get("/reports/DHG/preview/999").status_code == 404
    assert client.get("/reports/ZZZ/preview/1").status_code == 404


def test_get_reports_lists_export_backed_items(monkeypatch, tmp_path):
    class FakeStorage:
        def list_objects(self, bucket: str, prefix: str = "", limit: int = 1000, offset: int = 0):
            assert bucket == "exports"
            if prefix == "client_reports/DHG/":
                return [
                    {"name": "report.pdf", "updated_at": "2026-06-15T00:00:00+00:00", "size": 2048},
                    {"name": "explanation.pdf", "updated_at": "2026-06-15T00:00:01+00:00"},
                ]
            return []

    monkeypatch.setattr("backend.storage.SupabaseStorageAdapter", lambda: FakeStorage())
    client = _make_client(tmp_path, with_local_files=False)

    resp = client.get("/reports")
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "no-store"
    dhg = next(i for i in resp.json()["items"] if i["ticker"] == "DHG")
    assert dhg["has_report"] is True
    assert dhg["has_explanation"] is True
    assert dhg["report_size"] == 2048
    assert dhg["updated_at"] == "2026-06-15T00:00:01+00:00"
