from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from backend.api import create_app


def _client_pdf_bytes(label: bytes = b"report") -> bytes:
    return b"%PDF-1.4\n" + label + (b"\n0" * 6000)


@pytest.fixture(autouse=True)
def _disable_export_storage(monkeypatch):
    def _raise_unconfigured():
        raise ValueError("storage disabled in report endpoint tests")

    monkeypatch.setattr("backend.storage.SupabaseStorageAdapter", _raise_unconfigured)


def _make_client(tmp_path: Path, *, with_local_files: bool = True) -> TestClient:
    out = tmp_path / "output"
    out.mkdir()
    if with_local_files:
        (out / "DHG_report.pdf").write_bytes(_client_pdf_bytes(b"report"))
        (out / "DHG_explanation.pdf").write_bytes(_client_pdf_bytes(b"expl"))
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


def test_get_report_file_rejects_local_benchmark_stub(tmp_path):
    client = _make_client(tmp_path, with_local_files=False)
    out = tmp_path / "output"
    (out / "DHG_report.pdf").write_bytes(b"%PDF-1.4\nbenchmark_valuation_v1 analyst draft\n")

    listing = client.get("/reports")
    dhg = next(i for i in listing.json()["items"] if i["ticker"] == "DHG")
    assert dhg["has_report"] is False

    resp = client.get("/reports/DHG/file/report")
    assert resp.status_code == 404


def test_get_report_file_prefers_export_when_local_pdf_is_rejected(monkeypatch, tmp_path):
    class FakeStorage:
        def list_objects(self, bucket: str, prefix: str = "", limit: int = 1000, offset: int = 0):
            assert bucket == "exports"
            if prefix == "client_reports/DHG/":
                return [
                    {"name": "report.pdf", "updated_at": "2026-06-15T00:00:00+00:00", "size": 2048},
                    {"name": "explanation.pdf", "updated_at": "2026-06-15T00:00:01+00:00"},
                ]
            return []

        def download_bytes(self, bucket: str, path: str):
            assert bucket == "exports"
            assert path == "client_reports/DHG/report.pdf"
            return _client_pdf_bytes(b"export")

    monkeypatch.setattr("backend.storage.SupabaseStorageAdapter", lambda: FakeStorage())
    client = _make_client(tmp_path, with_local_files=False)
    out = tmp_path / "output"
    (out / "DHG_report.pdf").write_bytes(b"%PDF-1.4\nbenchmark_valuation_v1 analyst draft\n")

    listing = client.get("/reports")
    dhg = next(i for i in listing.json()["items"] if i["ticker"] == "DHG")
    assert dhg["has_report"] is True

    resp = client.get("/reports/DHG/file/report")
    assert resp.status_code == 200
    assert resp.content.startswith(b"%PDF")


class _FakeRuntimeStore:
    def __init__(self):
        self.created = []
        self.run = {
            "run_id": "r1",
            "ticker": "DHG",
            "run_type": "full_report",
            "status": "running",
            "current_stage": "ANALYZE",
            "flags_json": {"generate_mode": "full_pipeline", "source_run_id": "src1"},
            "request_json": {},
            "config_snapshot_json": {},
            "progress_json": {
                "stage_started_at": "2026-06-19T00:00:05+00:00",
                "last_heartbeat_at": "2026-06-19T00:00:10+00:00",
            },
            "created_at": "2026-06-19T00:00:00+00:00",
            "updated_at": "2026-06-19T00:00:10+00:00",
            "finished_at": None,
        }

    def get_run(self, run_id):
        return self.run if run_id == "r1" else None

    def create_run(self, **kwargs):
        self.created.append(kwargs)


class _FakeExecutor:
    def __init__(self):
        self.submitted = []

    def submit(self, context):
        self.submitted.append(context)

    def future_state(self, run_id):
        return "running"


def test_run_status_includes_generation_diagnostics():
    app = create_app(
        runtime_store=_FakeRuntimeStore(),
        run_executor=_FakeExecutor(),
        check_schema_on_startup=False,
    )
    client = TestClient(app)

    resp = client.get("/research/r1/status")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["mode"] == "full_pipeline"
    assert payload["source_run_id"] == "src1"
    assert payload["executor_state"] == "running"
    assert payload["stage_started_at"] == "2026-06-19T00:00:05+00:00"
    assert payload["last_heartbeat_at"] == "2026-06-19T00:00:10+00:00"
    assert isinstance(payload["elapsed_seconds"], int)


def test_generate_prefers_fast_render_for_existing_export(monkeypatch, tmp_path):
    store = _FakeRuntimeStore()
    executor = _FakeExecutor()
    app = create_app(runtime_store=store, run_executor=executor, check_schema_on_startup=False)
    out = tmp_path / "output"
    out.mkdir()
    csv = tmp_path / "universe.csv"
    csv.write_text(
        "ticker,company_name,exchange,segment,is_mvp,notes\n"
        "DHG,Duoc Hau Giang,HOSE,pharma,true,MVP core\n",
        encoding="utf-8",
    )
    app.state.report_output_dir = out
    app.state.report_universe_csv = csv

    monkeypatch.setattr("backend.api.ensure_ticker_registered_from_universe", lambda *args, **kwargs: None)
    monkeypatch.setattr("backend.dataops.snapshot_freshness.latest_ready_snapshot", lambda ticker: None)
    monkeypatch.setattr("backend.reporting.report_delivery.latest_renderable_run_id", lambda ticker: None)
    monkeypatch.setattr("backend.reporting.report_delivery.existing_client_report_available", lambda ticker: True)
    client = TestClient(app)

    resp = client.post("/reports/DHG/generate")

    assert resp.status_code == 200
    assert resp.json()["mode"] == "fast_render"
    flags = store.created[0]["flags"]
    assert flags["generate_mode"] == "fast_render"
    assert flags["generate_route_reason"] == "existing_export_only"
    assert flags["existing_export_available"] is True


def test_generate_force_full_ignores_existing_renderable_artifacts(monkeypatch, tmp_path):
    store = _FakeRuntimeStore()
    executor = _FakeExecutor()
    app = create_app(runtime_store=store, run_executor=executor, check_schema_on_startup=False)
    out = tmp_path / "output"
    out.mkdir()
    csv = tmp_path / "universe.csv"
    csv.write_text(
        "ticker,company_name,exchange,segment,is_mvp,notes\n"
        "DHG,Duoc Hau Giang,HOSE,pharma,true,MVP core\n",
        encoding="utf-8",
    )
    app.state.report_output_dir = out
    app.state.report_universe_csv = csv

    monkeypatch.setattr("backend.api.ensure_ticker_registered_from_universe", lambda *args, **kwargs: None)
    monkeypatch.setattr("backend.dataops.snapshot_freshness.latest_ready_snapshot", lambda ticker: True)
    monkeypatch.setattr("backend.reporting.report_delivery.latest_renderable_run_id", lambda ticker: "src-existing")
    monkeypatch.setattr("backend.reporting.report_delivery.existing_client_report_available", lambda ticker: True)
    client = TestClient(app)

    resp = client.post("/reports/DHG/generate?force_full=true")

    assert resp.status_code == 200
    assert resp.json()["mode"] == "full_pipeline"
    flags = store.created[0]["flags"]
    assert flags["generate_mode"] == "full_pipeline"
    assert flags["generate_route_reason"] == "force_full_refresh"
    assert flags["force_full_refresh"] is True
    assert "source_run_id" not in flags
