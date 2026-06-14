from pathlib import Path
from fastapi.testclient import TestClient
from backend.api import create_app


def _make_client(tmp_path: Path) -> TestClient:
    out = tmp_path / "output"
    out.mkdir()
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
    assert items[1]["has_report"] is False
