"""Smoke test: ClientReportPublisher orchestrates VM -> sections -> HTML -> PDF -> upload.

Collaborators are stubbed so the wiring is exercised without Supabase, a DB, or a
real browser PDF backend. This locks the contract PUBLISH depends on:
the publisher uploads ``report.html`` and ``report.pdf`` under the run key.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from backend.reporting import client_report_view_model as crvm
from backend.reporting import client_section_builder as csb
from backend.reporting import final_report_renderer as frr
from backend.reporting import html_renderer as hr
from backend.reporting import report_data_loader as rdl


class _FakeAdapter:
    def __init__(self) -> None:
        self.uploaded: list[tuple[str, str]] = []

    def checksum_file(self, path):
        return "checksum"

    def exists(self, bucket, path):
        return False

    def upload_file(self, bucket, path, local_path, content_type):
        self.uploaded.append((bucket, path))

    def validate_checksum(self, bucket, path, checksum):
        return True


class _FakeHTMLRenderer:
    def render(self, sections, ctx, output_dir, run_id, render_mode):
        assert render_mode == "client_final"
        assert sections and sections[0]["page"] == "snapshot"
        path = Path(output_dir) / f"{run_id}_{ctx.ticker}_report.html"
        path.write_text("<html><body>ok</body></html>", encoding="utf-8")
        return path


class _FakePDFRenderer:
    def render(self, html_path, output_dir, run_id, allow_stub, strict_preflight):
        assert strict_preflight is True and allow_stub is False
        path = Path(output_dir) / f"{run_id}_report.pdf"
        path.write_bytes(b"%PDF-1.4 fake")
        return path


def test_client_report_publisher_uploads_html_and_pdf(monkeypatch, tmp_path):
    monkeypatch.setattr(
        crvm, "build_client_report_view_model",
        lambda ticker, mode, run_id: SimpleNamespace(ticker=ticker, mode=mode),
    )
    monkeypatch.setattr(
        csb, "build_client_report_sections",
        lambda vm: [{"page": "snapshot", "markdown": "<p>cover</p>"}],
    )
    monkeypatch.setattr(
        rdl, "load_report_context",
        lambda ticker, run_id: SimpleNamespace(ticker=ticker, status="DRAFT"),
    )
    monkeypatch.setattr(hr, "HTMLRenderer", _FakeHTMLRenderer)
    monkeypatch.setattr(frr, "PDFRenderer", _FakePDFRenderer)

    adapter = _FakeAdapter()
    publisher = frr.ClientReportPublisher(storage_adapter=adapter, work_dir=tmp_path)

    published = publisher.publish(run_id="run-001", ticker="DHG", mode="client_final")

    assert published.html.storage_path == "run-001/report.html"
    assert published.pdf.storage_path == "run-001/report.pdf"
    assert published.html.artifact_type == "report_html"
    assert published.pdf.artifact_type == "report_pdf"
    assert {path for _, path in adapter.uploaded} == {
        "run-001/report.html",
        "run-001/report.pdf",
    }
