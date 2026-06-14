from pathlib import Path
import inspect
from unittest.mock import patch

from backend.reporting import report_delivery
from backend.storage.layout import client_report_key


class FakeStorage:
    def __init__(self) -> None:
        self.uploads: list[tuple] = []

    def upload_file(self, bucket, path, local_path, content_type, *, upsert=False):
        # Render must produce real files before upload.
        assert Path(local_path).is_file()
        self.uploads.append((bucket, path, Path(local_path).name, content_type, upsert))
        return {}


def _fake_render_client(*, run_id, ticker, mode, output_dir):
    pdf = Path(output_dir) / f"{ticker}_report.pdf"
    pdf.write_bytes(b"%PDF-1.4 report")
    return pdf.with_suffix(".html"), pdf, object()


def _fake_render_explanation(*, run_id, ticker, view_model, output_dir):
    pdf = Path(output_dir) / f"{ticker}_explanation.pdf"
    pdf.write_bytes(b"%PDF-1.4 explanation")
    return pdf.with_suffix(".html"), pdf


def test_client_report_key_is_ticker_stable():
    assert client_report_key("dhg", "report.pdf") == "client_reports/DHG/report.pdf"
    assert client_report_key("DHG", "explanation.pdf") == "client_reports/DHG/explanation.pdf"


def test_render_and_store_uploads_both_pdfs_to_exports():
    storage = FakeStorage()
    with patch.object(report_delivery, "render_client_report_to_directory", _fake_render_client), patch.object(
        report_delivery, "render_report_explanation_to_directory", _fake_render_explanation
    ):
        result = report_delivery.render_and_store("dhg", "run-1", storage=storage)

    assert result.report_key == "client_reports/DHG/report.pdf"
    assert result.explanation_key == "client_reports/DHG/explanation.pdf"
    # Both PDFs uploaded to the exports bucket, with upsert so newest wins.
    assert {u[0] for u in storage.uploads} == {"exports"}
    assert {u[1] for u in storage.uploads} == {
        "client_reports/DHG/report.pdf",
        "client_reports/DHG/explanation.pdf",
    }
    assert all(u[4] is True for u in storage.uploads)
    assert all(u[3] == "application/pdf" for u in storage.uploads)


def test_latest_renderable_run_accepts_report_model_or_draft_valuation_artifacts():
    source = inspect.getsource(report_delivery.latest_renderable_run_id)
    assert "report_candidate_model" in source
    assert "has_final_model OR (has_facts AND has_valuation AND has_manifest)" in source
    assert "storage_path IS NOT NULL" in source
