from __future__ import annotations

import json
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.harness.agent_registry import AgentConfig
from backend.harness.model_adapter import MAIN_MODEL, OpenAIModelAdapter
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


def test_runner_converts_tool_system_exit_to_runtime_failure(monkeypatch) -> None:
    runner = ResearchGraphRunner(store=MagicMock())
    state = ResearchGraphState(run_id="run_tool_exit", ticker="DHG", objective="tool exit")

    def exit_tool(*args, **kwargs):
        raise SystemExit(2)

    spec = SimpleNamespace(
        tool_id="build_facts",
        owner_agent_ids=("data_retrieval",),
        implementation=exit_tool,
        permission_level="test",
        artifact_producer_key="BUILD_FACTS",
    )
    monkeypatch.setattr(runner.tool_registry, "get_tool", lambda tool_id: spec)
    monkeypatch.setattr(
        runner.agent_registry,
        "get_agent_config",
        lambda agent_id: _agent_config("build_facts"),
    )

    with pytest.raises(RuntimeError, match="tool_process_exit: tool_id=build_facts exit_code=2"):
        runner._run_tool(state, "data_retrieval", "build_facts", "DHG", 2021, 2025)


def _diagnostic_agent_config() -> AgentConfig:
    return AgentConfig(
        agent_id="financial_analysis",
        role="FinancialAnalysisAgent",
        model=MAIN_MODEL,
        temperature=0.1,
        prompt_path="prompts/financial_analysis.md",
        prompt="System prompt for diagnostics.",
        allowed_tools=["read_snapshot"],
        output_schema="FinancialAnalysis",
        timeout_seconds=90,
        retry_policy="no_retry",
    )


def _diagnostic_from(exc: BaseException) -> dict[str, object]:
    prefix = "agent_llm_call_failed: "
    message = str(exc)
    assert message.startswith(prefix)
    return json.loads(message[len(prefix):])


def test_model_adapter_parses_fenced_typed_artifact_json() -> None:
    content = """```json
{"schema_version":"1.0","run_id":"run-1","ticker":"DHG","producer":"data_and_evidence_agent","checksum":"abc"}
```"""

    parsed = OpenAIModelAdapter._parse_response_json(content)

    assert parsed == {
        "schema_version": "1.0",
        "run_id": "run-1",
        "ticker": "DHG",
        "producer": "data_and_evidence_agent",
        "checksum": "abc",
    }


def test_validate_environment_missing_openai_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        OpenAIModelAdapter().validate_environment(
            agent_config=_diagnostic_agent_config(),
            state={"stage": "FINANCIAL_ANALYSIS"},
            task="Create typed financial analysis.",
        )


def test_run_agent_wraps_connection_error_with_diagnostic(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "test-secret-value"
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    # Force the plain-openai client path so the injected FakeOpenAI below is used.
    # With Langfuse configured, the adapter resolves langfuse.openai instead, which
    # would bypass the fake and hit the network (env-dependent flakiness).
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

    class FakeCompletions:
        def create(self, **_: object) -> object:
            raise ConnectionError("Connection error.")

    class FakeChat:
        completions = FakeCompletions()

    class FakeOpenAI:
        def __init__(self, **kwargs: object) -> None:
            self.chat = FakeChat()

    openai_module = types.ModuleType("openai")
    openai_module.OpenAI = FakeOpenAI
    monkeypatch.setitem(sys.modules, "openai", openai_module)

    with pytest.raises(RuntimeError) as exc_info:
        OpenAIModelAdapter().run_agent(
            agent_config=_diagnostic_agent_config(),
            state={
                "run_id": "run-1",
                "ticker": "DHG",
                "run_type": "full_report",
                "current_stage": "FINANCIAL_ANALYSIS",
                "objective": "diagnose llm errors",
            },
            task="Create typed financial analysis.",
            input_refs=["artifact-1"],
        )

    message = str(exc_info.value)
    assert secret not in message
    diagnostic = _diagnostic_from(exc_info.value)
    assert diagnostic["provider"] == "openai"
    assert diagnostic["model"] == MAIN_MODEL
    assert diagnostic["exception_type"] == "ConnectionError"
    assert diagnostic["exception_message"] == "Connection error."
    assert diagnostic["stage"] == "FINANCIAL_ANALYSIS"
    assert diagnostic["failure_stage"] == "chat_completions_create"
    assert diagnostic["agent_id"] == "financial_analysis"
    assert diagnostic["task"] == "Create typed financial analysis."
