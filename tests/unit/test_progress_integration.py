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
