from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def test_run_research_cli_exposes_only_canonical_harness_args() -> None:
    from scripts.run_research import parse_args

    args = parse_args([
        "--ticker", "dhg",
        "--from-year", "2022",
        "--to-year", "2025",
        "--ocr",
        "--auto-approve-assumptions",
        "--auto-approve-final",
    ])

    assert args.ticker == "dhg"
    assert args.from_year == 2022
    assert args.to_year == 2025
    assert args.ocr is True
    assert args.auto_approve_assumptions is True
    assert args.auto_approve_final is True
    assert not hasattr(args, "legacy_pipeline")
    assert not hasattr(args, "skip_ingest")


def test_run_research_cli_submits_through_full_report_orchestrator(monkeypatch) -> None:
    from scripts import run_research

    captured = {}
    store = MagicMock()
    store.get_run.return_value = None

    class FakeStore:
        def __init__(self, dsn=None):
            captured["dsn"] = dsn

        def check_schema_version(self):
            captured["schema_checked"] = True

        def create_run(self, **kwargs):
            captured["created_run"] = kwargs

    class FakeOrchestrator:
        def __init__(self, store, progress=None):
            captured["orchestrator_store"] = store
            captured["orchestrator_progress"] = progress

        def execute(self, context):
            captured["context"] = context

    monkeypatch.setattr("backend.runtime_store.RuntimeStore", FakeStore)
    monkeypatch.setattr("backend.orchestrator.FullReportOrchestrator", FakeOrchestrator)
    monkeypatch.setattr("backend.universe_registration.ensure_ticker_registered_from_universe", lambda store, ticker: None)
    monkeypatch.setattr(run_research, "_run_id", lambda ticker: "run_cli_orchestrator")

    args = run_research.parse_args([
        "--ticker", "dhg",
        "--from-year", "2022",
        "--to-year", "2024",
        "--auto-approve-assumptions",
        "--auto-approve-final",
    ])

    run_id = run_research.submit_harness_run(args)

    assert run_id == "run_cli_orchestrator"
    assert captured["schema_checked"] is True
    assert captured["created_run"]["run_type"] == "full_report"
    assert captured["context"].ticker == "DHG"
    assert captured["context"].from_year == 2022
    assert captured["context"].to_year == 2024
    assert captured["context"].policy["auto_approve_assumptions"] is True
    assert captured["context"].policy["auto_approve_final"] is True
    assert captured["orchestrator_progress"] is not None


def test_runner_execute_preserves_period_scope_and_ocr_flag(monkeypatch) -> None:
    from backend.harness.runner import ResearchGraphRunner
    from backend.orchestrator import RunContext

    captured = {}

    def fake_run_until_pause(self, state, start_stage="PREFLIGHT"):
        captured["from_year"] = state.from_year
        captured["to_year"] = state.to_year
        captured["ocr"] = state.ocr
        return state

    monkeypatch.setattr(ResearchGraphRunner, "run_until_pause", fake_run_until_pause)

    runner = ResearchGraphRunner(store=MagicMock())
    runner.execute(
        RunContext(
            run_id="run_scope_test",
            ticker="DHG",
            run_type="full_report",
            objective="scope test",
            policy={},
            flags={},
            from_year=2022,
            to_year=2024,
            ocr=True,
        )
    )

    assert captured == {"from_year": 2022, "to_year": 2024, "ocr": True}


def test_run_research_cli_raises_when_orchestrator_reports_failed_state(monkeypatch) -> None:
    from scripts import run_research

    class FakeStore:
        def __init__(self, dsn=None):
            pass

        def check_schema_version(self):
            pass

        def create_run(self, **kwargs):
            pass

    class FakeOrchestrator:
        def __init__(self, store, progress=None):
            pass

        def execute(self, context):
            return SimpleNamespace(
                status="failed",
                current_stage="RESEARCH_MANAGER_PLAN",
                blocking_reason="agent_llm_call_failed",
            )

    monkeypatch.setattr("backend.runtime_store.RuntimeStore", FakeStore)
    monkeypatch.setattr("backend.orchestrator.FullReportOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "backend.universe_registration.ensure_ticker_registered_from_universe",
        lambda store, ticker: None,
    )
    monkeypatch.setattr(run_research, "_run_id", lambda ticker: "run_failed")

    with pytest.raises(RuntimeError, match="run_id=run_failed"):
        run_research.submit_harness_run(run_research.parse_args(["--ticker", "DHG"]))
