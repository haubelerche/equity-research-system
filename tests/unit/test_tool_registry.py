from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.harness.runner import ResearchGraphRunner
from backend.harness.state import ResearchGraphState
from backend.harness.tool_registry import ToolRegistry


def _agent_config(*allowed_tools: str) -> SimpleNamespace:
    return SimpleNamespace(allowed_tools=list(allowed_tools))


def test_tool_registry_rejects_unimplemented_agent_tool() -> None:
    registry = ToolRegistry()

    with pytest.raises(ValueError, match="unimplemented tools"):
        registry.validate_agent_tool_policy({"financial_analyst": _agent_config("missing_tool")})


def test_tool_registry_rejects_non_owner_tool_assignment() -> None:
    registry = ToolRegistry()

    with pytest.raises(ValueError, match="non-owner agents"):
        registry.validate_agent_tool_policy({"supervisor": _agent_config("build_facts")})


def test_tool_registry_specs_are_complete_for_configured_tools() -> None:
    registry = ToolRegistry()
    configured = {
        "build_facts",
        "build_index",
        "read_snapshot",
        "read_ratio_artifact",
        "run_valuation",
        "read_valuation_artifact",
        "generate_report",
        "evaluate_report_quality",
    }

    for tool_id in configured:
        spec = registry.get_tool(tool_id)
        assert spec.tool_id == tool_id
        assert spec.implementation
        assert spec.owner_agent_ids
        assert spec.input_schema
        assert spec.output_schema == "ServiceNodeResult"
        assert spec.permission_level
        assert spec.timeout_seconds > 0
        assert spec.blocking_semantics
        assert spec.artifact_producer_key


def test_runner_blocks_tool_invocation_by_wrong_agent_role() -> None:
    runner = ResearchGraphRunner(store=MagicMock())
    state = ResearchGraphState(run_id="run_tool_policy", ticker="DHG", objective="policy test")

    with pytest.raises(PermissionError, match="not owned"):
        runner._run_tool(state, "supervisor", "build_facts", "DHG", 2021, 2025)


def test_runner_blocks_tool_not_declared_in_agent_allowed_tools(monkeypatch) -> None:
    runner = ResearchGraphRunner(store=MagicMock())
    state = ResearchGraphState(run_id="run_allowed_policy", ticker="DHG", objective="allowed policy test")
    spec = SimpleNamespace(
        tool_id="build_facts",
        owner_agent_ids=("data_retrieval",),
        implementation=lambda *args, **kwargs: None,
        permission_level="test",
        artifact_producer_key="BUILD_FACTS",
    )

    monkeypatch.setattr(runner.tool_registry, "get_tool", lambda tool_id: spec)
    monkeypatch.setattr(runner.agent_registry, "get_agent_config", lambda agent_id: _agent_config())

    with pytest.raises(PermissionError, match="allowed_tools"):
        runner._run_tool(state, "data_retrieval", "build_facts", "DHG", 2021, 2025)
