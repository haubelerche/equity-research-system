"""Regression: INGEST_AND_VALIDATE reuses a fresh snapshot when available.

When latest_ready_snapshot returns a dict, auto_ingest and build_index must NOT
be called, but build_facts MUST be called.  When it returns None the full ingest
path (auto_ingest + build_facts + build_index) must run.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from backend.harness.runner import ResearchGraphRunner
from backend.harness.state import ResearchGraphState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _runner() -> ResearchGraphRunner:
    r = ResearchGraphRunner.__new__(ResearchGraphRunner)
    r.store = MagicMock()
    return r


def _state() -> ResearchGraphState:
    return ResearchGraphState(
        run_id="r1",
        ticker="DHG",
        run_type="full_report",
        objective="o",
        policy={},
        flags={},
        from_year=2022,
        to_year=2025,
    )


def _fake_tool_result(snapshot_id: str = "snap_x") -> MagicMock:
    res = MagicMock()
    res.summary = {"snapshot_id": snapshot_id}
    res.artifact_refs = []
    res.evidence_refs = []
    res.node_name = "t"
    res.output_hash = "h"
    res.gate_inputs = {}
    res.blocking_reason = None
    return res


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@patch(
    "backend.harness.runner.data_quality_gate",
    return_value={"gate": "DATA_QUALITY_GATE", "passed": True},
)
@patch("backend.dataops.snapshot_freshness.latest_ready_snapshot")
def test_fresh_snapshot_skips_auto_ingest_and_build_index(mock_latest, _gate):
    """When a fresh snapshot exists, only build_facts runs; auto_ingest and build_index are skipped."""
    mock_latest.return_value = {"snapshot_id": "snap_x", "status": "active"}

    runner = _runner()
    called: list[str] = []

    def fake_run_tool(state, agent, tool, *a, **k):
        called.append(tool)
        return _fake_tool_result()

    runner._run_tool = fake_run_tool
    runner._merge_result = lambda *a, **k: None
    runner._record_gate = lambda *a, **k: None

    runner._execute_stage(_state(), "INGEST_AND_VALIDATE")

    assert "build_facts" in called, "build_facts must run when reusing snapshot"
    assert "auto_ingest" not in called, "auto_ingest must be skipped when snapshot is fresh"
    assert "build_index" not in called, "build_index must be skipped when snapshot is fresh"


@patch(
    "backend.harness.runner.data_quality_gate",
    return_value={"gate": "DATA_QUALITY_GATE", "passed": True},
)
@patch("backend.dataops.snapshot_freshness.latest_ready_snapshot", return_value=None)
def test_no_snapshot_runs_full_ingest(_mock_latest, _gate):
    """When no fresh snapshot exists, all three tools (auto_ingest, build_facts, build_index) run."""
    runner = _runner()
    called: list[str] = []

    def fake_run_tool(state, agent, tool, *a, **k):
        called.append(tool)
        return _fake_tool_result()

    runner._run_tool = fake_run_tool
    runner._merge_result = lambda *a, **k: None
    runner._record_gate = lambda *a, **k: None

    runner._execute_stage(_state(), "INGEST_AND_VALIDATE")

    assert "auto_ingest" in called, "auto_ingest must run when no fresh snapshot"
    assert "build_facts" in called, "build_facts must run when no fresh snapshot"
    assert "build_index" in called, "build_index must run when no fresh snapshot"


@patch(
    "backend.harness.runner.data_quality_gate",
    return_value={"gate": "DATA_QUALITY_GATE", "passed": True},
)
@patch("backend.dataops.snapshot_freshness.latest_ready_snapshot")
def test_force_ingest_policy_bypasses_snapshot_reuse(mock_latest, _gate):
    """force_ingest policy must bypass snapshot reuse and run the full ingest path."""
    mock_latest.return_value = {"snapshot_id": "snap_x", "status": "active"}

    runner = _runner()
    called: list[str] = []

    def fake_run_tool(state, agent, tool, *a, **k):
        called.append(tool)
        return _fake_tool_result()

    runner._run_tool = fake_run_tool
    runner._merge_result = lambda *a, **k: None
    runner._record_gate = lambda *a, **k: None

    state = _state()
    state.policy = {"force_ingest": True}

    runner._execute_stage(state, "INGEST_AND_VALIDATE")

    assert "auto_ingest" in called, "force_ingest must trigger full ingest (auto_ingest)"
    assert "build_index" in called, "force_ingest must trigger full ingest (build_index)"
    # latest_ready_snapshot should NOT even be called when force_ingest is set
    mock_latest.assert_not_called()


@patch(
    "backend.harness.runner.data_quality_gate",
    return_value={"gate": "DATA_QUALITY_GATE", "passed": True},
)
@patch("backend.dataops.snapshot_freshness.latest_ready_snapshot")
def test_snapshot_lookup_failure_falls_through_to_full_ingest(mock_latest, _gate):
    """If latest_ready_snapshot raises, the warning is logged and full ingest proceeds."""
    mock_latest.side_effect = RuntimeError("db connection closed")

    runner = _runner()
    called: list[str] = []

    def fake_run_tool(state, agent, tool, *a, **k):
        called.append(tool)
        return _fake_tool_result()

    runner._run_tool = fake_run_tool
    runner._merge_result = lambda *a, **k: None
    runner._record_gate = lambda *a, **k: None

    runner._execute_stage(_state(), "INGEST_AND_VALIDATE")

    assert "auto_ingest" in called, "full ingest must run after snapshot lookup failure"
    assert "build_facts" in called
    assert "build_index" in called


@patch(
    "backend.harness.runner.data_quality_gate",
    return_value={"gate": "DATA_QUALITY_GATE", "passed": True},
)
@patch("backend.dataops.snapshot_freshness.latest_ready_snapshot")
def test_reuse_snapshot_id_propagated_to_state(mock_latest, _gate):
    """snapshot_id from build_facts result (or fallback to reuse_snapshot) is stored on state."""
    mock_latest.return_value = {"snapshot_id": "snap_fallback", "status": "active"}

    runner = _runner()

    # build_facts returns a result with its own snapshot_id
    def fake_run_tool(state, agent, tool, *a, **k):
        res = MagicMock()
        res.summary = {"snapshot_id": "snap_from_facts"}
        res.artifact_refs = []
        res.evidence_refs = []
        res.node_name = "t"
        res.output_hash = "h"
        res.gate_inputs = {}
        res.blocking_reason = None
        return res

    runner._run_tool = fake_run_tool
    runner._merge_result = lambda *a, **k: None
    runner._record_gate = lambda *a, **k: None

    state = _state()
    runner._execute_stage(state, "INGEST_AND_VALIDATE")

    # build_facts' snapshot_id takes precedence
    assert state.snapshot_id == "snap_from_facts"
