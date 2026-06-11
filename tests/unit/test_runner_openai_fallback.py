from __future__ import annotations

from types import SimpleNamespace

from backend.harness.agent_registry import AgentConfig
from backend.harness.model_adapter import CHEAP_MODEL, MAIN_MODEL
from backend.harness.progress import ProgressReporter
from backend.harness.runner import ResearchGraphRunner
from backend.harness.state import AgentResult, ResearchGraphState


def test_run_agent_retries_with_fallback_on_primary_llm_failure(monkeypatch) -> None:
    config = AgentConfig(
        agent_id="research_manager",
        role="ResearchManagerAgent",
        model=MAIN_MODEL,
        temperature=0.1,
        prompt_path="prompts/research_manager.md",
        prompt="prompt",
        output_schema="ResearchManagerArtifact",
        timeout_seconds=60,
        retry_policy="no_retry",
    )

    class Registry:
        def get_agent_config(self, agent_id: str) -> AgentConfig:
            assert agent_id == "research_manager"
            return config

    class PrimaryAdapter:
        def run_agent(self, **kwargs):
            raise RuntimeError("agent_llm_call_failed: credit balance exhausted")

    class FallbackAdapter:
        def __init__(self) -> None:
            self.calls = 0

        def run_agent(self, *, agent_config, **kwargs):
            self.calls += 1
            assert agent_config.model == CHEAP_MODEL
            return AgentResult(
                agent_id=agent_config.agent_id,
                action="fallback",
                status="completed",
                payload={"schema_version": "1.0", "producer": "research_manager"},
                confidence=0.8,
            )

    fallback_adapter = FallbackAdapter()
    monkeypatch.setattr(
        "backend.harness.runner.create_model_adapter",
        lambda model: fallback_adapter,
    )
    monkeypatch.setattr(
        "backend.harness.contracts.validate_agent_artifact",
        lambda schema, payload: None,
    )

    runner = object.__new__(ResearchGraphRunner)
    runner.agent_registry = Registry()
    runner.model_adapter = PrimaryAdapter()
    runner.settings = SimpleNamespace(fallback_model=CHEAP_MODEL)
    runner.progress = ProgressReporter(quiet=True)
    runner._charge_agent_step = lambda *args, **kwargs: None  # type: ignore[method-assign]

    state = ResearchGraphState(
        run_id="run_test",
        ticker="DHG",
        objective="test",
        current_stage="PLAN",
    )

    result = runner._run_agent(state, "research_manager", "Plan")

    assert fallback_adapter.calls == 1
    assert result.fallback_triggered is True
    assert f"fallback_model_used:{CHEAP_MODEL}" in result.warnings
