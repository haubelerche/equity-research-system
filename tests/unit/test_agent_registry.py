from __future__ import annotations

from pathlib import Path

import pytest

from backend.harness.agent_registry import AgentRegistry, REQUIRED_PROMPT_SECTIONS
from backend.harness.model_adapter import OpenAIModelAdapter


def test_agent_registry_loads_five_product_agents() -> None:
    registry = AgentRegistry()
    configs = registry.load()
    assert set(configs) == {
        "supervisor",
        "data_retrieval",
        "financial_analyst",
        "valuation",
        "report_writer_critic",
    }
    for cfg in configs.values():
        for section in REQUIRED_PROMPT_SECTIONS:
            assert section in cfg.prompt


def test_model_adapter_requires_openai_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        OpenAIModelAdapter().validate_environment()


def test_agent_registry_rejects_unsupported_tools(tmp_path: Path) -> None:
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    prompt = "\n".join(REQUIRED_PROMPT_SECTIONS)
    (prompt_dir / "supervisor.md").write_text(prompt, encoding="utf-8")
    config = tmp_path / "agents.yml"
    config.write_text(
        """
agents:
  supervisor:
    role: SupervisorAgent
    model: gpt-4o
    prompt_path: prompts/supervisor.md
    allowed_tools: [approve_report]
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Unsupported tools"):
        AgentRegistry(config).load()
