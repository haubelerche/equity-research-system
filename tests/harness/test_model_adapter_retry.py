"""Regression: transient LLM read/connection errors must be retried before failing the run.

IncompleteRead and similar transient network errors on the first attempt should be
retried up to 3 times; only after exhausting retries does the existing rich diagnostic
path raise RuntimeError('agent_llm_call_failed: ...').
"""
from __future__ import annotations

import http.client
import types

import pytest

from backend.harness.agent_registry import AgentConfig
from backend.harness.model_adapter import MAIN_MODEL, OpenAIModelAdapter


def _make_agent_config() -> AgentConfig:
    """Build a minimal valid AgentConfig for run_agent testing."""
    # The prompt must contain all REQUIRED_PROMPT_SECTIONS from agent_registry.py,
    # but for model_adapter tests we bypass AgentRegistry.load() and construct directly.
    minimal_prompt = "\n".join([
        "# Objective",
        "Test agent.",
        "# Allowed Inputs",
        "state dict.",
        "# Forbidden Actions",
        "None.",
        "# Output JSON Schema",
        '{"status": "string"}',
        "# Uncertainty Language",
        "Use hedging.",
        "# Source And Citation Discipline",
        "Cite sources.",
        "# Escalation Conditions",
        "On failure.",
        "# Project Disclaimer Boundary",
        "Standard disclaimer.",
    ])
    return AgentConfig(
        agent_id="test_agent",
        role="ResearchManagerAgent",
        model=MAIN_MODEL,
        temperature=0.0,
        prompt_path="config/agents/prompts/test.txt",
        prompt=minimal_prompt,
        allowed_tools=[],
        output_schema="GenericResult",
        budget_class="reasoning",
        timeout_seconds=30,
        retry_policy="no_retry",
    )


class _FakeResp:
    """Minimal stand-in for an OpenAI chat completion response."""

    class _Choice:
        finish_reason = "stop"
        message = types.SimpleNamespace(
            content='{"status":"completed","payload":{"ok":true},"confidence":0.9}'
        )

    choices = [_Choice()]
    usage = types.SimpleNamespace(prompt_tokens=10, completion_tokens=5)


def test_transient_read_error_is_retried(monkeypatch):
    """First attempt raises IncompleteRead; second attempt succeeds."""
    calls = {"n": 0}

    def flaky(self, client, create_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise http.client.IncompleteRead(b"partial")
        return _FakeResp()

    monkeypatch.setattr(OpenAIModelAdapter, "_create_completion", flaky)
    monkeypatch.setattr("time.sleep", lambda *_a, **_k: None)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    state = {"current_stage": "TEST"}
    result = OpenAIModelAdapter().run_agent(
        agent_config=_make_agent_config(),
        state=state,
        task="test_task",
        input_refs=[],
    )

    assert calls["n"] == 2, f"expected 2 attempts, got {calls['n']}"
    assert result.status == "completed"


def test_non_transient_error_is_not_retried(monkeypatch):
    """A non-transient ValueError must NOT be retried; it must still raise agent_llm_call_failed."""
    calls = {"n": 0}

    def always_bad(self, client, create_kwargs):
        calls["n"] += 1
        raise ValueError("bad request — not a transient error")

    monkeypatch.setattr(OpenAIModelAdapter, "_create_completion", always_bad)
    monkeypatch.setattr("time.sleep", lambda *_a, **_k: None)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    state = {"current_stage": "TEST"}
    with pytest.raises(RuntimeError, match="agent_llm_call_failed"):
        OpenAIModelAdapter().run_agent(
            agent_config=_make_agent_config(),
            state=state,
            task="test_task",
            input_refs=[],
        )

    assert calls["n"] == 1, f"non-transient errors must not be retried; got {calls['n']} calls"


def test_exhausted_retries_raise_agent_llm_call_failed(monkeypatch):
    """If all 3 retry attempts fail with a transient error, raise agent_llm_call_failed."""
    calls = {"n": 0}

    def always_transient(self, client, create_kwargs):
        calls["n"] += 1
        raise http.client.IncompleteRead(b"partial")

    monkeypatch.setattr(OpenAIModelAdapter, "_create_completion", always_transient)
    monkeypatch.setattr("time.sleep", lambda *_a, **_k: None)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    state = {"current_stage": "TEST"}
    with pytest.raises(RuntimeError, match="agent_llm_call_failed"):
        OpenAIModelAdapter().run_agent(
            agent_config=_make_agent_config(),
            state=state,
            task="test_task",
            input_refs=[],
        )

    assert calls["n"] == 3, f"expected 3 attempts before giving up, got {calls['n']}"
