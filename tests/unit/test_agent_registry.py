from __future__ import annotations

from pathlib import Path

import pytest

from backend.harness.agent_registry import AgentRegistry, REQUIRED_PROMPT_SECTIONS
from backend.harness.model_adapter import OpenAIModelAdapter
from backend.settings import settings


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
        assert cfg.model == settings.default_model_name


def test_agent_registry_resolves_model_env_placeholder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
    model: ${TEST_AGENT_MODEL}
    prompt_path: prompts/supervisor.md
    allowed_tools: []
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("TEST_AGENT_MODEL", "gpt-test-model")

    cfg = AgentRegistry(config).get_agent_config("supervisor")

    assert cfg.model == "gpt-test-model"


def test_model_adapter_requires_provider_key(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        OpenAIModelAdapter().validate_environment()


def test_financial_analyst_prompt_has_all_required_sections():
    """AgentRegistry must load financial_analyst config without error — validates all 8 sections."""
    registry = AgentRegistry()
    configs = registry.load()
    assert "financial_analyst" in configs
    cfg = configs["financial_analyst"]
    assert cfg.role == "FinancialAnalystAgent"
    for section in REQUIRED_PROMPT_SECTIONS:
        assert section in cfg.prompt, f"Missing required section in financial_analyst.md: {section}"


def test_financial_analyst_prompt_has_output_schema_fields():
    """financial_analyst.md must define the 5 narrative output fields in its Output JSON Schema."""
    registry = AgentRegistry()
    cfg = registry.load()["financial_analyst"]
    required_fields = [
        "financial_narrative",
        "investment_thesis",
        "risk_narrative",
        "forecast_narrative",
        "key_data_quality_notes",
    ]
    for field in required_fields:
        assert field in cfg.prompt, f"Narrative field '{field}' not defined in Output JSON Schema"


def test_financial_analyst_prompt_specifies_vietnamese_output():
    """financial_analyst.md must explicitly request Vietnamese language output."""
    registry = AgentRegistry()
    cfg = registry.load()["financial_analyst"]
    # Must mention Vietnamese output in some form
    assert any(term in cfg.prompt for term in ["tiếng Việt", "Vietnamese", "Việt"]), (
        "Prompt does not specify Vietnamese output language"
    )


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
