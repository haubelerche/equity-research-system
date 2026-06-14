"""Deterministic renderer for approved ``final_report_model`` artifacts.

This module deliberately renders only the already-assembled model. It does not
load legacy report inputs, discover files, or synthesize missing narrative.
"""
from __future__ import annotations

import html
import json
import logging
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from backend.reporting.pdf_renderer import PDFRenderError, PDFRenderer
from backend.reporting.publication_readiness import (
    ClientFinalAuthorization,
    assert_client_final_authorization,
    authorize_client_final,
)
from backend.reporting.report_assembler import ReportAssembler, ReportAssemblyError
from backend.storage import RUNS_BUCKET, SupabaseStorageAdapter, run_artifact_key
from backend.utils import deterministic_id

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PublishedReportArtifact:
    artifact_id: str
    artifact_type: str
    section_key: str
    storage_bucket: str
    storage_path: str
    checksum: str
    content_type: str
    file_size_bytes: int
    version: int = 1
    is_locked: bool = True
    producer: str = "render_and_publish"

    def to_ref(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "section_key": self.section_key,
            "version": self.version,
            "storage_bucket": self.storage_bucket,
            "storage_path": self.storage_path,
            "checksum": self.checksum,
            "content_type": self.content_type,
            "file_size_bytes": self.file_size_bytes,
            "is_locked": self.is_locked,
            "producer": self.producer,
        }


@dataclass(frozen=True)
class PublishedReport:
    html: PublishedReportArtifact
    pdf: PublishedReportArtifact
    workings: PublishedReportArtifact | None = None
    explanation: PublishedReportArtifact | None = None

    def artifact_refs(self) -> list[dict[str, Any]]:
        refs = [self.html.to_ref(), self.pdf.to_ref()]
        if self.workings is not None:
            refs.append(self.workings.to_ref())
        if self.explanation is not None:
            refs.append(self.explanation.to_ref())
        return refs

    def to_dict(self) -> dict[str, Any]:
        out = {
            "html": self.html.to_ref(),
            "pdf": self.pdf.to_ref(),
        }
        if self.workings is not None:
            out["workings_md"] = self.workings.to_ref()
        if self.explanation is not None:
            out["explanation_pdf"] = self.explanation.to_ref()
        return out


def _publish_run_file(
    storage_adapter: SupabaseStorageAdapter,
    *,
    run_id: str,
    ticker: str,
    artifact_name: str,
    local_path: Path,
    artifact_type: str,
    section_key: str,
    content_type: str,
) -> PublishedReportArtifact:
    """Upload one rendered file to the ``runs`` bucket with checksum guards."""
    storage_path = run_artifact_key(run_id, artifact_name)
    checksum = storage_adapter.checksum_file(local_path)
    if storage_adapter.exists(RUNS_BUCKET, storage_path):
        if not storage_adapter.validate_checksum(RUNS_BUCKET, storage_path, checksum):
            raise FileExistsError(
                f"Refusing overwrite with different checksum: {RUNS_BUCKET}/{storage_path}"
            )
    else:
        storage_adapter.upload_file(RUNS_BUCKET, storage_path, local_path, content_type)
    if not storage_adapter.validate_checksum(RUNS_BUCKET, storage_path, checksum):
        raise RuntimeError(f"Checksum validation failed: {RUNS_BUCKET}/{storage_path}")
    return PublishedReportArtifact(
        artifact_id=deterministic_id(run_id, artifact_type, checksum),
        artifact_type=artifact_type,
        section_key=section_key,
        storage_bucket=RUNS_BUCKET,
        storage_path=storage_path,
        checksum=checksum,
        content_type=content_type,
        file_size_bytes=local_path.stat().st_size,
        producer=f"render_and_publish:{ticker.upper()}",
    )


class FinalReportRenderer:
    """Render an approved final report model into local report.html/report.pdf."""

    def __init__(self, pdf_renderer: PDFRenderer | None = None) -> None:
        self.pdf_renderer = pdf_renderer or PDFRenderer()

    def render_to_directory(
        self,
        final_report_model: Mapping[str, Any],
        output_dir: Path | str,
        *,
        authorization: ClientFinalAuthorization | None = None,
    ) -> tuple[Path, Path]:
        assert_client_final_authorization(
            authorization,
            run_id=str(final_report_model.get("run_id") or ""),
            ticker=str(final_report_model.get("ticker") or ""),
        )
        validation = ReportAssembler().validate_final_report_model(final_report_model)
        if not validation.valid:
            raise ReportAssemblyError(validation)

        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        html_path = output / "report.html"
        html_path.write_text(render_final_report_model_html(final_report_model), encoding="utf-8")

        pdf_path = self.pdf_renderer.render(
            html_path,
            output_dir=output,
            run_id="",
            allow_stub=False,
            strict_preflight=True,
        )
        if pdf_path.suffix.lower() != ".pdf":
            raise PDFRenderError(f"Strict PDF renderer returned non-PDF artifact: {pdf_path}")
        return html_path, pdf_path


class FinalReportPublisher:
    """Render and persist approved report artifacts under the run storage key."""

    def __init__(
        self,
        *,
        renderer: FinalReportRenderer | None = None,
        storage_adapter: SupabaseStorageAdapter | None = None,
        work_dir: Path | str | None = None,
        authorization_provider: Callable[..., ClientFinalAuthorization] | None = None,
    ) -> None:
        self.renderer = renderer or FinalReportRenderer()
        self.storage_adapter = storage_adapter or SupabaseStorageAdapter()
        self.work_dir = Path(work_dir) if work_dir is not None else None
        self.authorization_provider = authorization_provider or authorize_client_final

    def publish(
        self,
        *,
        run_id: str,
        ticker: str,
        final_report_model: Mapping[str, Any],
    ) -> PublishedReport:
        temporary_dir: Path | None = None
        if self.work_dir is None:
            temporary_dir = Path(tempfile.mkdtemp(prefix=f"render-{run_id}-"))
            render_dir = temporary_dir
        else:
            render_dir = self.work_dir

        try:
            authorization = self.authorization_provider(run_id=run_id, ticker=ticker)
            html_path, pdf_path = self.renderer.render_to_directory(
                final_report_model,
                render_dir,
                authorization=authorization,
            )
            html_artifact = self._persist_file(
                run_id=run_id,
                ticker=ticker,
                artifact_name="report.html",
                local_path=html_path,
                artifact_type="report_html",
                section_key="report_html",
                content_type="text/html; charset=utf-8",
            )
            pdf_artifact = self._persist_file(
                run_id=run_id,
                ticker=ticker,
                artifact_name="report.pdf",
                local_path=pdf_path,
                artifact_type="report_pdf",
                section_key="report_pdf",
                content_type="application/pdf",
            )
            return PublishedReport(html=html_artifact, pdf=pdf_artifact)
        finally:
            if temporary_dir is not None:
                shutil.rmtree(temporary_dir, ignore_errors=True)

    def _persist_file(
        self,
        *,
        run_id: str,
        ticker: str,
        artifact_name: str,
        local_path: Path,
        artifact_type: str,
        section_key: str,
        content_type: str,
    ) -> PublishedReportArtifact:
        return _publish_run_file(
            self.storage_adapter,
            run_id=run_id,
            ticker=ticker,
            artifact_name=artifact_name,
            local_path=local_path,
            artifact_type=artifact_type,
            section_key=section_key,
            content_type=content_type,
        )


def render_client_report_to_directory(
    *,
    run_id: str,
    ticker: str,
    mode: str,
    output_dir: Path | str,
    authorization: ClientFinalAuthorization | None = None,
) -> tuple[Path, Path, Any]:
    """Render a client report locally with the current chart pipeline."""
    if mode == "client_final":
        assert_client_final_authorization(
            authorization,
            run_id=run_id,
            ticker=ticker,
        )
    from backend.reporting.client_chart_builder import build_client_report_charts
    from backend.reporting.client_report_view_model import build_client_report_view_model
    from backend.reporting.client_section_builder import build_client_report_sections
    from backend.reporting.html_renderer import HTMLRenderer
    from backend.reporting.report_data_loader import load_report_context

    render_dir = Path(output_dir)
    render_dir.mkdir(parents=True, exist_ok=True)
    view_model = build_client_report_view_model(ticker, mode, run_id=run_id)
    view_model.charts.update(
        build_client_report_charts(view_model, render_dir / "charts", run_id=run_id)
    )
    sections = build_client_report_sections(view_model)
    context = load_report_context(ticker, run_id=run_id)
    html_path = HTMLRenderer().render(
        sections,
        context,
        output_dir=render_dir,
        run_id=run_id,
        render_mode=str(mode),
    )
    pdf_path = PDFRenderer().render(
        html_path,
        output_dir=render_dir,
        run_id=run_id,
        allow_stub=False,
        strict_preflight=True,
    )
    if pdf_path.suffix.lower() != ".pdf":
        raise PDFRenderError(f"Strict PDF renderer returned non-PDF artifact: {pdf_path}")
    try:
        from backend.reporting.post_render_audit import audit_client_final_render

        audit = audit_client_final_render(html_path, pdf_path)
        if not audit.passed:
            existing = list(getattr(view_model, "display_blocking_reasons", []) or [])
            view_model.display_blocking_reasons = sorted(
                set([*existing, *audit.blocking_reasons])
            )
    except Exception as exc:  # noqa: BLE001
        _logger.warning("post-render audit unavailable for run_id=%s: %s", run_id, exc)
    return html_path, pdf_path, view_model


def render_report_explanation_to_directory(
    *,
    run_id: str,
    ticker: str,
    view_model: Any,
    output_dir: Path | str,
) -> tuple[Path, Path]:
    """Render the calculation and reasoning companion as standalone HTML/PDF."""
    import markdown

    from backend.reporting import valuation_workings as vw

    render_dir = Path(output_dir)
    render_dir.mkdir(parents=True, exist_ok=True)
    inputs = vw.load_workings_inputs(run_id)
    body_md = vw.build_report_explanation_md(
        ticker=ticker,
        run_id=run_id,
        view_model=view_model,
        **inputs,
    )
    body_html = markdown.markdown(
        body_md,
        extensions=["tables", "fenced_code", "nl2br", "sane_lists"],
    )
    html_path = render_dir / f"{ticker.upper()}_explanation.html"
    html_path.write_text(
        _render_explanation_html(ticker=ticker, run_id=run_id, body_html=body_html),
        encoding="utf-8",
    )
    pdf_path = PDFRenderer().render(
        html_path,
        output_dir=render_dir,
        run_id="",
        allow_stub=False,
        strict_preflight=True,
    )
    if pdf_path.suffix.lower() != ".pdf":
        raise PDFRenderError(f"Strict PDF renderer returned non-PDF artifact: {pdf_path}")
    return html_path, pdf_path


class ClientReportPublisher:
    """Render the broker-quality client report from locked run artifacts and publish it.

    Reads locked artifacts through the Supabase-backed run manifest, builds the
    client view model, renders the ACBS-style HTML + PDF, and uploads them under the
    run storage key. LLM prose flows in via the ``financial_analysis`` narrative
    fields, preserving the doctrine that Python computes and the LLM only drafts.
    """

    def __init__(
        self,
        *,
        storage_adapter: SupabaseStorageAdapter | None = None,
        work_dir: Path | str | None = None,
        authorization_provider: Callable[..., ClientFinalAuthorization] | None = None,
    ) -> None:
        self.storage_adapter = storage_adapter or SupabaseStorageAdapter()
        self.work_dir = Path(work_dir) if work_dir is not None else None
        self.authorization_provider = authorization_provider or authorize_client_final

    def publish(
        self,
        *,
        run_id: str,
        ticker: str,
        mode: str = "client_final",
    ) -> PublishedReport:
        temporary_dir: Path | None = None
        if self.work_dir is None:
            temporary_dir = Path(tempfile.mkdtemp(prefix=f"client-render-{run_id}-"))
            render_dir = temporary_dir
        else:
            render_dir = self.work_dir

        try:
            authorization = (
                self.authorization_provider(run_id=run_id, ticker=ticker)
                if mode == "client_final"
                else None
            )
            html_path, pdf_path, view_model = render_client_report_to_directory(
                run_id=run_id,
                ticker=ticker,
                mode=mode,
                output_dir=render_dir,
                authorization=authorization,
            )
            html_artifact = _publish_run_file(
                self.storage_adapter,
                run_id=run_id,
                ticker=ticker,
                artifact_name="report.html",
                local_path=html_path,
                artifact_type="report_html",
                section_key="report_html",
                content_type="text/html; charset=utf-8",
            )
            pdf_artifact = _publish_run_file(
                self.storage_adapter,
                run_id=run_id,
                ticker=ticker,
                artifact_name="report.pdf",
                local_path=pdf_path,
                artifact_type="report_pdf",
                section_key="report_pdf",
                content_type="application/pdf",
            )
            workings_artifact = self._build_and_publish_workings(
                run_id=run_id,
                ticker=ticker,
                view_model=view_model,
                render_dir=render_dir,
            )
            explanation_artifact = self._build_and_publish_explanation(
                run_id=run_id,
                ticker=ticker,
                view_model=view_model,
                render_dir=render_dir,
            )
            return PublishedReport(
                html=html_artifact,
                pdf=pdf_artifact,
                workings=workings_artifact,
                explanation=explanation_artifact,
            )
        finally:
            if temporary_dir is not None:
                shutil.rmtree(temporary_dir, ignore_errors=True)

    def _build_and_publish_workings(
        self,
        *,
        run_id: str,
        ticker: str,
        view_model: Any,
        render_dir: Path,
    ) -> PublishedReportArtifact | None:
        """Render the valuation workings .md alongside the report. Non-fatal on failure."""
        from backend.reporting import valuation_workings as vw

        try:
            inputs = vw.load_workings_inputs(run_id)
            markdown = vw.build_valuation_workings_md(
                ticker=ticker,
                run_id=run_id,
                view_model=view_model,
                **inputs,
            )
            workings_path = render_dir / "report_workings.md"
            workings_path.write_text(markdown, encoding="utf-8")
            return _publish_run_file(
                self.storage_adapter,
                run_id=run_id,
                ticker=ticker,
                artifact_name="report_workings.md",
                local_path=workings_path,
                artifact_type="report_workings_md",
                section_key="report_workings_md",
                content_type="text/markdown; charset=utf-8",
            )
        except Exception as exc:  # noqa: BLE001
            _logger.warning(
                "valuation workings .md build failed for run_id=%s: %s", run_id, exc
            )
            return None

    def _build_and_publish_explanation(
        self,
        *,
        run_id: str,
        ticker: str,
        view_model: Any,
        render_dir: Path,
    ) -> PublishedReportArtifact | None:
        """Render and publish the user-facing calculation/reasoning companion."""
        try:
            _, explanation_path = render_report_explanation_to_directory(
                run_id=run_id,
                ticker=ticker,
                view_model=view_model,
                output_dir=render_dir,
            )
            return _publish_run_file(
                self.storage_adapter,
                run_id=run_id,
                ticker=ticker,
                artifact_name="report_explanation.pdf",
                local_path=explanation_path,
                artifact_type="report_explanation_pdf",
                section_key="report_explanation_pdf",
                content_type="application/pdf",
            )
        except Exception as exc:  # noqa: BLE001
            _logger.warning(
                "report explanation PDF build failed for run_id=%s: %s", run_id, exc
            )
            return None


def _render_explanation_html(*, ticker: str, run_id: str, body_html: str) -> str:
    """Return compact print-oriented HTML for the explanation companion."""
    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8" />
<title>{html.escape(ticker.upper())} - Giải trình báo cáo</title>
<style>
@page {{ size: A4; margin: 12mm 11mm 14mm; }}
body {{ font-family: Arial, sans-serif; color: #172033; font-size: 10pt; line-height: 1.34; }}
h1 {{ color: #123b6d; font-size: 18pt; border-bottom: 1.4px solid #123b6d; padding-bottom: 4pt; margin: 0 0 7pt; }}
h2 {{ color: #123b6d; font-size: 12pt; margin: 9pt 0 4pt; page-break-after: avoid; }}
h3 {{ color: #315b86; font-size: 10.5pt; margin: 7pt 0 3pt; page-break-after: avoid; }}
p {{ margin: 3pt 0 5pt; }}
table {{ width: 100%; border-collapse: collapse; margin: 5pt 0 7pt; font-size: 8.8pt; page-break-inside: auto; }}
th, td {{ border: 0.5pt solid #b9c5d3; padding: 2.6pt 3pt; vertical-align: top; }}
th {{ background: #eaf0f6; color: #123b6d; }}
tr {{ page-break-inside: auto; }}
code {{ color: #7b2d26; font-size: 8.8pt; }}
blockquote {{ margin: 5pt 0; padding: 5pt 7pt; background: #f2f5f8; border-left: 2.2pt solid #6086ad; }}
.meta {{ color: #607080; font-size: 8pt; }}
</style>
</head>
<body>
<p class="meta">Mã cổ phiếu: {html.escape(ticker.upper())}</p>
{body_html}
</body>
</html>
"""


def render_final_report_model_html(final_report_model: Mapping[str, Any]) -> str:
    """Return deterministic standalone HTML for an assembled final report model."""
    ticker = str(final_report_model.get("ticker") or "")
    run_id = str(final_report_model.get("run_id") or "")
    checksum = str(final_report_model.get("checksum") or "")
    sections = final_report_model.get("sections") or {}

    section_html = []
    if isinstance(sections, Mapping):
        for section_key, section_payload in sections.items():
            section_html.append(
                "\n".join(
                    [
                        '<section class="report-section">',
                        f"<h2>{html.escape(_titleize(str(section_key)))}</h2>",
                        _render_value(section_payload),
                        "</section>",
                    ]
                )
            )

    return "\n".join(
        [
            "<!DOCTYPE html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8" />',
            '<meta name="viewport" content="width=device-width, initial-scale=1" />',
            f"<title>{html.escape(ticker)} Final Report</title>",
            "<style>",
            "body { font-family: Arial, sans-serif; margin: 32px; color: #111827; }",
            "header { border-bottom: 1px solid #d1d5db; margin-bottom: 24px; }",
            "h1 { font-size: 24px; margin: 0 0 8px; }",
            "h2 { font-size: 18px; margin-top: 24px; color: #1f2937; }",
            "dl { display: grid; grid-template-columns: 180px 1fr; gap: 6px 14px; }",
            "dt { font-weight: 700; color: #374151; }",
            "dd { margin: 0; }",
            "pre { white-space: pre-wrap; background: #f9fafb; padding: 10px; }",
            "li { margin-bottom: 4px; }",
            ".meta { color: #6b7280; font-size: 12px; }",
            "</style>",
            "</head>",
            "<body>",
            "<header>",
            f"<h1>{html.escape(ticker)} Final Report</h1>",
            f'<p class="meta">Run: {html.escape(run_id)} | Model checksum: {html.escape(checksum)}</p>',
            "</header>",
            *section_html,
            "</body>",
            "</html>",
        ]
    )


def _render_value(value: Any) -> str:
    if isinstance(value, Mapping):
        items = []
        for key in sorted(value, key=str):
            items.append(
                f"<dt>{html.escape(str(key))}</dt><dd>{_render_value(value[key])}</dd>"
            )
        return "<dl>" + "".join(items) + "</dl>"
    if isinstance(value, (list, tuple)):
        return "<ul>" + "".join(f"<li>{_render_value(item)}</li>" for item in value) + "</ul>"
    if value is None:
        return "<p></p>"
    if isinstance(value, (str, int, float, bool)):
        text = html.escape(str(value)).replace("\n", "<br />")
        return f"<p>{text}</p>"
    return "<pre>" + html.escape(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)) + "</pre>"


def _titleize(section_key: str) -> str:
    return section_key.replace("_", " ").title()
