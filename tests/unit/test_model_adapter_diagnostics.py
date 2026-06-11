from __future__ import annotations

import pytest

from backend.harness.agent_registry import AgentConfig
from backend.harness.model_adapter import MAIN_MODEL, OpenAIModelAdapter


def _agent_config() -> AgentConfig:
    return AgentConfig(
        agent_id="research_manager",
        role="ResearchManagerAgent",
        model=MAIN_MODEL,
        temperature=0.1,
        prompt_path="prompts/research_manager.md",
        prompt="# Objective\nTest prompt",
        allowed_tools=[],
        output_schema="ResearchManagerArtifact",
        timeout_seconds=90,
        retry_policy="no_retry",
    )


def test_missing_openai_key_error(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        OpenAIModelAdapter().validate_environment(
            agent_config=_agent_config(),
            state={"current_stage": "PLAN", "run_id": "run-1"},
            task="Create the typed research plan.",
        )


def test_financial_analysis_context_omits_non_financial_artifacts() -> None:
    state = {
        "stage": "FINANCIAL_ANALYSIS",
        "input_artifacts": {
            "evidence_pack": {"large": "x" * 1000},
            "index": {"chunks_indexed": 500},
            "build_facts": {"valuation_gate": "pass"},
            "ratios": {"ratios": {"net_margin": {"2025FY": 0.16}}},
            "snapshot": {
                "sample_facts": [
                    {
                        "ticker": "DHG",
                        "fiscal_year": 2025,
                        "fiscal_period": "FY",
                        "line_item_code": "revenue.net",
                        "value": 5266.9,
                        "unit": "vnd_bn",
                        "source_tier": 1,
                        "source_uri": "official://dhg/2025",
                        "raw_page_text": "should not be sent",
                        "ingested_at": "2026-06-10T00:00:00Z",
                    }
                ],
            },
        },
    }

    compact = OpenAIModelAdapter._compact_state(state)
    artifacts = compact["input_artifacts"]

    assert set(artifacts) == {"build_facts", "ratios", "snapshot"}
    fact = artifacts["snapshot"]["sample_facts"][0]
    assert fact["line_item_code"] == "revenue.net"
    assert "raw_page_text" not in fact
    assert "ingested_at" not in fact
