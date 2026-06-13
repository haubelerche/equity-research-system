"""Regression: Langfuse tracing must be wired into the OpenAI adapter.

Commit eaae830 rewrote model_adapter.py and dropped the Langfuse instrumentation
that previously sent one trace per agent call. Production then moved from the
Anthropic drop-in to plain `openai.OpenAI`, so no traces reached Langfuse at all.

These tests pin the contract:
- When Langfuse credentials are present, the adapter uses the Langfuse OpenAI
  drop-in and attaches `name` + `metadata` (incl. langfuse_session_id=run_id) to
  the completion call so every agent of a run groups under one session.
- When credentials are absent, the adapter uses plain openai with NO extra
  kwargs (plain openai rejects unknown `name`/`metadata` kwargs).
"""
from __future__ import annotations

import types

from backend.harness.agent_registry import AgentConfig
from backend.harness.model_adapter import MAIN_MODEL, OpenAIModelAdapter


def _make_agent_config() -> AgentConfig:
    minimal_prompt = "\n".join([
        "# Objective", "Test agent.",
        "# Allowed Inputs", "state dict.",
        "# Forbidden Actions", "None.",
        "# Output JSON Schema", '{"status": "string"}',
        "# Uncertainty Language", "Use hedging.",
        "# Source And Citation Discipline", "Cite sources.",
        "# Escalation Conditions", "On failure.",
        "# Project Disclaimer Boundary", "Standard disclaimer.",
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
    class _Choice:
        finish_reason = "stop"
        message = types.SimpleNamespace(
            content='{"status":"completed","payload":{"ok":true},"confidence":0.9}'
        )

    choices = [_Choice()]
    usage = types.SimpleNamespace(prompt_tokens=10, completion_tokens=5)


def _run_capturing_kwargs(monkeypatch) -> dict:
    """Run one agent call and return the create_kwargs the adapter built."""
    captured: dict = {}

    def capture(self, client, create_kwargs):
        captured.update(create_kwargs)
        return _FakeResp()

    monkeypatch.setattr(OpenAIModelAdapter, "_create_completion", capture)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    state = {"current_stage": "TEST", "run_id": "run_abc123", "ticker": "DBD", "run_type": "full_report"}
    OpenAIModelAdapter().run_agent(
        agent_config=_make_agent_config(),
        state=state,
        task="test_task",
        input_refs=[],
    )
    return captured


def test_tracing_kwargs_present_when_langfuse_configured(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")

    kwargs = _run_capturing_kwargs(monkeypatch)

    assert kwargs.get("name") == "test_agent"
    meta = kwargs.get("metadata")
    assert isinstance(meta, dict)
    assert meta.get("langfuse_session_id") == "run_abc123"
    assert meta.get("agent_id") == "test_agent"
    assert meta.get("ticker") == "DBD"


def test_no_tracing_kwargs_when_langfuse_absent(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

    kwargs = _run_capturing_kwargs(monkeypatch)

    # Plain openai rejects unknown kwargs — these must NOT be present.
    assert "name" not in kwargs
    assert "metadata" not in kwargs
