from __future__ import annotations

import io
from unittest.mock import MagicMock
from backend.harness.progress import ProgressReporter


def test_runner_accepts_progress_parameter():
    from backend.harness.runner import ResearchGraphRunner
    buf = io.StringIO()
    reporter = ProgressReporter(stream=buf)
    store = MagicMock()
    runner = ResearchGraphRunner(store=store, progress=reporter)
    assert runner.progress is reporter


def test_runner_defaults_to_quiet_progress():
    from backend.harness.runner import ResearchGraphRunner
    store = MagicMock()
    runner = ResearchGraphRunner(store=store)
    assert runner.progress is not None
    assert runner.progress._quiet is True


def test_runner_heartbeat_writes_progress_diagnostics():
    from backend.harness.runner import ResearchGraphRunner
    from backend.harness.state import ResearchGraphState

    store = MagicMock()
    runner = ResearchGraphRunner(store=store)
    state = ResearchGraphState(
        run_id="r1",
        ticker="DHG",
        objective="x",
        current_stage="ANALYZE",
        flags={"generate_mode": "full_pipeline", "source_run_id": "src1"},
    )

    runner._heartbeat(state, operation="agent_start:financial_analysis", substep="financial_analysis")

    _, kwargs = store.update_run_progress.call_args
    assert kwargs["operation"] == "agent_start:financial_analysis"
    assert kwargs["substep"] == "financial_analysis"
    assert kwargs["mode"] == "full_pipeline"
    assert kwargs["source_run_id"] == "src1"
    assert "last_heartbeat_at" in kwargs
