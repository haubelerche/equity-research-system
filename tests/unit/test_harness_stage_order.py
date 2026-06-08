"""Behavioral test: DATA_RETRIEVAL_RUN must call auto_ingest before build_facts.

Uses fake tool functions — no DB or filesystem access.
"""
from unittest.mock import MagicMock
import pytest


def _make_fake_result(name: str):
    from backend.harness.state import ServiceNodeResult, stable_hash
    return ServiceNodeResult(
        node_name=name,
        status="completed",
        summary={"ticker": "DHG", "snapshot_id": None},
        output_hash=stable_hash({"ticker": "DHG"}),
        artifact_refs=[],
    )


def _make_fake_agent_result():
    from backend.harness.state import AgentResult
    return AgentResult(
        status="completed",
        agent_id="test_agent",
        payload={"review": "ok"},
        confidence=1.0,
    )


def test_data_retrieval_run_calls_auto_ingest_before_build_facts(monkeypatch):
    """Verify auto_ingest_tool is invoked before build_facts_tool in DATA_RETRIEVAL_RUN."""
    call_order: list[str] = []

    def fake_auto_ingest(ticker, from_year, to_year, ocr=False):
        call_order.append("auto_ingest")
        return _make_fake_result("AUTO_INGEST")

    def fake_build_facts(ticker, from_year, to_year):
        call_order.append("build_facts")
        return _make_fake_result("BUILD_FACTS")

    def fake_build_index(ticker, from_year, to_year, **kw):
        call_order.append("build_index")
        return _make_fake_result("BUILD_INDEX")

    monkeypatch.setattr("backend.harness.runner.auto_ingest_tool", fake_auto_ingest)
    monkeypatch.setattr("backend.harness.runner.build_facts_tool", fake_build_facts)
    monkeypatch.setattr("backend.harness.runner.build_index_tool", fake_build_index)

    from backend.harness.state import ResearchGraphState
    from backend.harness.runner import ResearchGraphRunner

    store = MagicMock()
    runner = ResearchGraphRunner(store=store)
    state = ResearchGraphState(run_id="test_001", ticker="DHG", from_year=2021, to_year=2025, objective="test")
    runner._run_agent = MagicMock(return_value=_make_fake_agent_result())
    runner._merge_result = MagicMock()
    runner._merge_agent_result = MagicMock()

    runner._execute_stage(state, "DATA_RETRIEVAL_RUN")

    assert "auto_ingest" in call_order, "auto_ingest_tool was not called"
    assert "build_facts" in call_order, "build_facts_tool was not called"
    assert call_order.index("auto_ingest") < call_order.index("build_facts"), (
        f"auto_ingest must run BEFORE build_facts, got order: {call_order}"
    )
