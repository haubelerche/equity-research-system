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

    # Whitelisted artifacts are kept; non-whitelisted are omitted.
    assert {"build_facts", "ratios", "snapshot"} <= set(artifacts)
    assert "evidence_pack" not in artifacts
    assert "index" not in artifacts
    # Omitted keys summary included for LLM awareness.
    assert "_omitted_artifact_keys" in artifacts
    assert sorted(artifacts["_omitted_artifact_keys"]) == ["evidence_pack", "index"]

    fact = artifacts["snapshot"]["sample_facts"][0]
    assert fact["line_item_code"] == "revenue.net"
    assert "raw_page_text" not in fact
    assert "ingested_at" not in fact


# ---------------------------------------------------------------------------
# Stage-specific compaction tests
# ---------------------------------------------------------------------------

_FULL_ARTIFACTS = {
    "auto_ingest": {"status": "ok"},
    "build_facts": {"snapshot_id": "snap1", "facts": 100},
    "index": {"chunks_indexed": 500},
    "evidence_pack": {"large": "x" * 2000},
    "snapshot": {"sample_facts": [], "snapshot_id": "snap1"},
    "ratios": {"net_margin": 0.16},
    "financial_analysis": {"revenue_trend": "growing"},
    "forecast_model": {"revenue_forecast": {}},
    "forecast_narrative": {"narrative": "text"},
    "valuation": {"has_fcff": True, "has_blend": True},
    "valuation_read": {"storage_path": "/some/path"},
    "valuation_proposal": {"method": "FCFF"},
    "valuation_review": {"approved": True},
    "market_snapshot": {"price": 120000},
    "readiness_review": {"ready": True},
    "research_lock": {"locked": True},
    "report_draft": {"sections": {}},
    "quality": {"overall_score": 0.85},
    "critic_review": {"decision": "pass"},
}


def _compact_for_stage(stage: str) -> dict:
    state = {"current_stage": stage, "artifacts": dict(_FULL_ARTIFACTS)}
    return OpenAIModelAdapter._compact_state(state)["artifacts"]


def test_plan_stage_gets_no_artifacts() -> None:
    arts = _compact_for_stage("PLAN")
    assert "_omitted_artifact_keys" in arts or len(arts) == 0
    for key in _FULL_ARTIFACTS:
        assert key not in arts


def test_ingest_stage_gets_only_ingest_artifacts() -> None:
    arts = _compact_for_stage("INGEST_AND_VALIDATE")
    assert "auto_ingest" in arts
    assert "build_facts" in arts
    assert "index" in arts
    assert "financial_analysis" not in arts
    assert "valuation" not in arts


def test_forecast_stage_gets_analysis_not_ingest() -> None:
    arts = _compact_for_stage("FORECAST_AND_VALUE")
    assert "financial_analysis" in arts
    assert "snapshot" in arts
    assert "forecast_model" in arts
    assert "valuation" in arts
    # Ingest-only artifacts excluded.
    assert "auto_ingest" not in arts
    assert "build_facts" not in arts
    assert "evidence_pack" not in arts


def test_write_report_stage_gets_analysis_and_valuation() -> None:
    arts = _compact_for_stage("WRITE_REPORT")
    assert "financial_analysis" in arts
    assert "forecast_model" in arts
    assert "valuation" in arts
    assert "market_snapshot" in arts
    # Raw ingest excluded.
    assert "auto_ingest" not in arts
    assert "snapshot" not in arts


def test_review_stage_gets_report_and_quality() -> None:
    arts = _compact_for_stage("REVIEW")
    assert "report_draft" in arts
    assert "valuation" in arts
    assert "quality" in arts
    assert "critic_review" in arts
    # Upstream raw data excluded.
    assert "snapshot" not in arts
    assert "forecast_model" not in arts
    assert "auto_ingest" not in arts


def test_truncate_large_dict_below_limit() -> None:
    small = {"a": 1, "b": "hello"}
    assert OpenAIModelAdapter._truncate_large_dict(small) == small


def test_truncate_large_dict_above_limit() -> None:
    big = {"small_key": 42, "big_key": list(range(5000))}
    result = OpenAIModelAdapter._truncate_large_dict(big, max_chars=1000)
    assert result["small_key"] == 42
    assert "truncated" in str(result["big_key"]).lower()
