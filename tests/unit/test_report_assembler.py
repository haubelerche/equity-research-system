from __future__ import annotations

import copy
import hashlib
from pathlib import Path
from typing import Any

import pytest

from backend.harness.runner import ResearchGraphRunner
from backend.harness.state import ResearchGraphState
from backend.reporting.final_report_renderer import (
    FinalReportPublisher,
    FinalReportRenderer,
    PublishedReport,
    PublishedReportArtifact,
)
from backend.reporting.pdf_renderer import PDFRenderError
from backend.reporting.report_assembler import (
    REQUIRED_SECTIONS,
    ReportAssembler,
    ReportAssemblyError,
    assemble_report,
)


def _inputs() -> tuple[dict, dict, dict]:
    draft = {
        "schema_version": "1.0",
        "run_id": "run-001",
        "ticker": "DBD",
        "producer": "thesis_report_agent",
        "sections": {
            name: {"key_message": f"authored:{name}", "supporting_values": [101, 202]}
            for name in reversed(REQUIRED_SECTIONS)
        },
        "claims": [{"claim_id": "c1", "text": "Authored claim 101"}],
        "limitations": ["Authored limitation"],
    }
    artifacts = {
        "claim_ledger": {
            "run_id": "run-001",
            "ticker": "DBD",
            "claims": [{"claim_id": "c1", "supporting_refs": ["valuation:value"]}],
        },
        "financial_analysis": {"run_id": "run-001", "ticker": "DBD", "revenue": 101},
        "forecast_model": {"run_id": "run-001", "ticker": "DBD", "eps": [10, 12]},
        "valuation": {"run_id": "run-001", "ticker": "DBD", "target_price": 202},
        "market_snapshot": {"run_id": "run-001", "ticker": "DBD", "current_price": 101},
    }
    specs = {
        "chart_specs": {"run_id": "run-001", "ticker": "DBD", "charts": [{"id": "c1"}]},
        "table_specs": {"run_id": "run-001", "ticker": "DBD", "tables": [{"id": "t1"}]},
    }
    return draft, artifacts, specs


def test_assemble_orders_and_copies_only_authored_content() -> None:
    draft, artifacts, specs = _inputs()
    originals = copy.deepcopy((draft, artifacts, specs))

    model = ReportAssembler().assemble(draft, artifacts, specs)

    assert tuple(model["sections"]) == REQUIRED_SECTIONS
    assert model["sections"]["company_overview"] == draft["sections"]["company_overview"]
    assert model["claim_ledger"] == artifacts["claim_ledger"]
    assert model["source_artifacts"]["valuation"] == artifacts["valuation"]
    assert model["chart_specs"] == specs["chart_specs"]
    assert model["table_specs"] == specs["table_specs"]
    assert (draft, artifacts, specs) == originals


def test_assembly_is_deterministic_and_result_does_not_alias_inputs() -> None:
    draft, artifacts, specs = _inputs()

    first = assemble_report(draft, artifacts, specs)
    second = assemble_report(draft, artifacts, specs)
    first["sections"]["company_overview"]["supporting_values"].append(999)

    assert first["checksum"] == second["checksum"]
    assert 999 not in draft["sections"]["company_overview"]["supporting_values"]
    assert ReportAssembler().validate_final_report_model(second).valid


def test_missing_required_section_fails_instead_of_filling_content() -> None:
    draft, artifacts, specs = _inputs()
    del draft["sections"]["valuation_and_recommendation"]

    validation = ReportAssembler().validate(draft, artifacts, specs)

    assert not validation.valid
    assert "missing required sections: valuation_and_recommendation" in validation.errors
    with pytest.raises(ReportAssemblyError, match="valuation_and_recommendation"):
        ReportAssembler().assemble(draft, artifacts, specs)


def test_missing_artifact_or_spec_fails() -> None:
    draft, artifacts, specs = _inputs()
    del artifacts["forecast_model"]
    del specs["chart_specs"]

    validation = ReportAssembler().validate(draft, artifacts, specs)

    assert "missing or invalid required artifact: forecast_model" in validation.errors
    assert "missing or invalid required spec: chart_specs" in validation.errors


def test_mismatched_artifact_identity_fails() -> None:
    draft, artifacts, specs = _inputs()
    artifacts["valuation"]["ticker"] = "DHG"

    validation = ReportAssembler().validate(draft, artifacts, specs)

    assert validation.errors == (
        "valuation.ticker does not match report_draft.ticker",
    )


def test_explicit_keyword_inputs_are_supported() -> None:
    draft, artifacts, specs = _inputs()

    model = ReportAssembler().assemble(draft, **artifacts, **specs)

    assert model["ticker"] == "DBD"
    assert model["source_artifacts"]["market_snapshot"]["current_price"] == 101


def test_validation_detects_modified_final_model() -> None:
    draft, artifacts, specs = _inputs()
    model = ReportAssembler().assemble(draft, artifacts, specs)
    model["source_artifacts"]["valuation"]["target_price"] = 303

    validation = ReportAssembler().validate_final_report_model(model)

    assert validation.errors == ("final report checksum mismatch",)


class FakePDFRenderer:
    def render(
        self,
        html_path: Path,
        output_dir: Path | str | None = None,
        run_id: str = "",
        allow_stub: bool = False,
        forbidden_terms: tuple[str, ...] | None = None,
        strict_preflight: bool = False,
    ) -> Path:
        assert run_id == ""
        assert allow_stub is False
        assert strict_preflight is True
        pdf_path = Path(output_dir or html_path.parent) / "report.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n% deterministic test pdf\n")
        return pdf_path


class FakeStorageAdapter:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.content_types: dict[tuple[str, str], str | None] = {}

    @staticmethod
    def checksum_file(local_path: str | Path) -> str:
        return hashlib.sha256(Path(local_path).read_bytes()).hexdigest()

    def exists(self, bucket: str, path: str) -> bool:
        return (bucket, path) in self.objects

    def upload_file(
        self,
        bucket: str,
        path: str,
        local_path: str | Path,
        content_type: str | None,
    ) -> dict[str, Any]:
        self.objects[(bucket, path)] = Path(local_path).read_bytes()
        self.content_types[(bucket, path)] = content_type
        return {}

    def validate_checksum(self, bucket: str, path: str, expected_checksum: str) -> bool:
        payload = self.objects.get((bucket, path))
        if payload is None:
            return False
        return hashlib.sha256(payload).hexdigest() == expected_checksum


def test_final_report_publisher_creates_run_html_and_pdf_refs(tmp_path: Path) -> None:
    adapter = FakeStorageAdapter()
    publisher = FinalReportPublisher(
        renderer=FinalReportRenderer(pdf_renderer=FakePDFRenderer()),
        storage_adapter=adapter,  # type: ignore[arg-type]
        work_dir=tmp_path,
    )

    published = publisher.publish(
        run_id="run-001",
        ticker="DBD",
        final_report_model=assemble_report(*_inputs()),
    )

    html_key = ("runs", "run-001/report.html")
    pdf_key = ("runs", "run-001/report.pdf")
    assert html_key in adapter.objects
    assert pdf_key in adapter.objects
    assert adapter.content_types[html_key] == "text/html; charset=utf-8"
    assert adapter.content_types[pdf_key] == "application/pdf"
    assert b"DBD Final Report" in adapter.objects[html_key]
    assert b"Cover Investment Summary" in adapter.objects[html_key]
    assert [ref["artifact_type"] for ref in published.artifact_refs()] == [
        "report_html",
        "report_pdf",
    ]


class FakeStore:
    def __init__(self) -> None:
        self.saved_artifacts: list[dict[str, Any]] = []
        self.updates: list[dict[str, Any]] = []

    def update_run_state(
        self,
        run_id: str,
        status: str,
        stage: str,
        flags: dict[str, Any] | None = None,
        finished: bool = False,
    ) -> None:
        self.updates.append(
            {
                "run_id": run_id,
                "status": status,
                "stage": stage,
                "finished": finished,
            }
        )

    def save_artifact(self, **kwargs: Any) -> None:
        self.saved_artifacts.append(kwargs)


class FakePublisher:
    def __init__(self, *, fail_pdf: bool = False) -> None:
        self.calls = 0
        self.fail_pdf = fail_pdf

    def publish(
        self,
        *,
        run_id: str,
        ticker: str,
        final_report_model: dict[str, Any],
    ) -> PublishedReport:
        self.calls += 1
        if self.fail_pdf:
            raise PDFRenderError("No usable PDF backend is available for strict export.")
        return PublishedReport(
            html=PublishedReportArtifact(
                artifact_id="html-id",
                artifact_type="report_html",
                section_key="report_html",
                storage_bucket="runs",
                storage_path=f"{run_id}/report.html",
                checksum="html-checksum",
                content_type="text/html; charset=utf-8",
                file_size_bytes=17,
            ),
            pdf=PublishedReportArtifact(
                artifact_id="pdf-id",
                artifact_type="report_pdf",
                section_key="report_pdf",
                storage_bucket="runs",
                storage_path=f"{run_id}/report.pdf",
                checksum="pdf-checksum",
                content_type="application/pdf",
                file_size_bytes=23,
            ),
        )


def _runner_state(*, approved: bool) -> ResearchGraphState:
    state = ResearchGraphState(
        run_id="run-001",
        ticker="DBD",
        objective="render publish test",
        current_stage="RENDER_AND_PUBLISH",
        artifacts={
            "final_report_model": assemble_report(*_inputs()),
            "report": {"snapshot_id": "snap-1"},
        },
        draft_report={"snapshot_id": "snap-1"},
    )
    if approved:
        state.approvals["final_report"] = "approved"
        state.human_review_decisions["final_report"] = {
            "decision": "approved",
            "reviewer": "analyst",
            "feedback_patch": {},
        }
    return state


def _runner_with_publisher(publisher: FakePublisher) -> tuple[ResearchGraphRunner, FakeStore]:
    store = FakeStore()
    runner = object.__new__(ResearchGraphRunner)
    runner.store = store
    runner.report_publisher = publisher
    from backend.harness.progress import ProgressReporter
    runner.progress = ProgressReporter(quiet=True)

    def write_evidence_packet(state: ResearchGraphState) -> None:
        state.artifact_refs.append(
            {
                "artifact_id": "evidence",
                "artifact_type": "evidence_packet_json",
                "section_key": "evidence_packet",
                "version": 1,
                "storage_bucket": "runs",
                "storage_path": f"{state.run_id}/evidence_pack.json",
                "checksum": "evidence-checksum",
            }
        )

    runner._write_evidence_packet = write_evidence_packet  # type: ignore[method-assign]
    return runner, store


def test_render_stage_does_not_publish_without_final_approval() -> None:
    publisher = FakePublisher()
    runner, store = _runner_with_publisher(publisher)

    state = runner._execute_stage(_runner_state(approved=False), "RENDER_AND_PUBLISH")

    assert publisher.calls == 0
    assert store.saved_artifacts == []
    assert state.status == "needs_human_review"
    assert "final_human_approval_missing" in (state.blocking_reason or "")


def test_render_stage_persists_artifact_refs_after_final_approval() -> None:
    publisher = FakePublisher()
    runner, store = _runner_with_publisher(publisher)

    state = runner._execute_stage(_runner_state(approved=True), "RENDER_AND_PUBLISH")

    assert publisher.calls == 1
    assert state.status == "approved"
    assert [artifact["artifact_type"] for artifact in store.saved_artifacts] == [
        "report_html",
        "report_pdf",
    ]
    assert {ref["section_key"] for ref in state.artifact_refs} >= {
        "report_html",
        "report_pdf",
    }
    assert store.updates[-1] == {
        "run_id": "run-001",
        "status": "approved",
        "stage": "RENDER_AND_PUBLISH",
        "finished": True,
    }


def test_render_stage_continues_when_supabase_publisher_fails() -> None:
    publisher = FakePublisher(fail_pdf=True)
    runner, store = _runner_with_publisher(publisher)

    state = runner._execute_stage(_runner_state(approved=True), "RENDER_AND_PUBLISH")

    # Local-first render succeeds; Supabase failure is non-blocking
    assert publisher.calls == 1
    assert state.status == "approved"
    assert any("supabase_upload_skipped" in e for e in state.errors)
