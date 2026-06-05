from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any

from backend.harness.agent_registry import AgentConfig
from backend.harness.state import AgentResult

# Pricing per million tokens (claude-haiku-4-5-20251001 rates)
_INPUT_COST_PER_M = {"claude-haiku-4-5-20251001": 0.80, "claude-sonnet-4-6": 3.00, "claude-opus-4-8": 15.00}
_OUTPUT_COST_PER_M = {"claude-haiku-4-5-20251001": 4.00, "claude-sonnet-4-6": 15.00, "claude-opus-4-8": 75.00}
_DEFAULT_INPUT_COST = 0.80
_DEFAULT_OUTPUT_COST = 4.00


class AnthropicModelAdapter:
    def validate_environment(self) -> None:
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY is required for 5-agent harness execution")
        try:
            import anthropic  # noqa: F401
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("anthropic package is required for agent execution") from exc

    def run_agent(
        self,
        agent_config: AgentConfig,
        state: dict[str, Any],
        task: str,
        input_refs: list[str] | None = None,
    ) -> AgentResult:
        self.validate_environment()

        # Use langfuse.anthropic drop-in if langfuse is configured; otherwise plain anthropic.
        try:
            from langfuse.anthropic import Anthropic
        except Exception:  # noqa: BLE001
            from anthropic import Anthropic

        run_id: str = state.get("run_id") or ""
        ticker: str = state.get("ticker") or ""
        lf_trace_id: str = hashlib.md5(run_id.encode()).hexdigest()

        started = time.perf_counter()
        client = Anthropic()
        state_payload = self._compact_state(state)
        user_payload = {
            "task": task,
            "input_refs": input_refs or [],
            "state": state_payload,
            "required_output": {
                "status": "completed|needs_review|failed",
                "payload": {},
                "confidence": 0.0,
                "confidence_breakdown": {},
                "requires_human": False,
                "review_reason": None,
                "warnings": [],
                "next_action": None,
            },
        }

        kwargs: dict[str, Any] = {
            "model": agent_config.model,
            "max_tokens": 4096,
            "temperature": agent_config.temperature,
            "system": agent_config.prompt,
            "messages": [
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False, default=str)},
            ],
        }
        # Langfuse v4 tracing params (ignored when using plain anthropic client)
        if hasattr(client, "messages") and hasattr(client, "_langfuse"):
            kwargs.update({
                "name": agent_config.agent_id,
                "trace_id": lf_trace_id,
                "metadata": {
                    "ticker": ticker,
                    "agent_id": agent_config.agent_id,
                    "task": task[:300],
                    "stage": state.get("current_stage"),
                    "run_type": state.get("run_type"),
                },
            })

        response = client.messages.create(**kwargs)
        latency_ms = int((time.perf_counter() - started) * 1000)
        content = response.content[0].text if response.content else "{}"
        try:
            raw = json.loads(content)
        except json.JSONDecodeError:
            raw = {
                "status": "needs_review",
                "payload": {"raw_response": content},
                "confidence": 0.0,
                "confidence_breakdown": {"json_validity": 0.0},
                "requires_human": True,
                "review_reason": "model_returned_malformed_json",
                "warnings": ["model_returned_malformed_json"],
            }

        usage = getattr(response, "usage", None)
        prompt_tokens = getattr(usage, "input_tokens", 0) if usage else 0
        completion_tokens = getattr(usage, "output_tokens", 0) if usage else 0
        status = raw.get("status", "needs_review")
        if status not in {"completed", "needs_review", "failed", "skipped"}:
            status = "needs_review"
        confidence = float(raw.get("confidence", 0.0) or 0.0)
        confidence = max(0.0, min(1.0, confidence))
        return AgentResult(
            agent_id=agent_config.agent_id,
            action=task,
            status=status,
            input_summary={"input_refs": input_refs or [], "state_stage": state.get("current_stage") or state.get("stage")},
            output_summary=raw.get("output_summary", {}),
            payload=raw.get("payload", {}),
            artifact_refs=raw.get("artifact_refs", []),
            evidence_refs=raw.get("evidence_refs", []),
            confidence=confidence,
            confidence_breakdown=raw.get("confidence_breakdown", {}),
            next_action=raw.get("next_action"),
            requires_human=bool(raw.get("requires_human", False)),
            review_reason=raw.get("review_reason"),
            blocking_reason=raw.get("blocking_reason"),
            warnings=raw.get("warnings", []),
            sources_used=raw.get("sources_used", []),
            latency_ms=latency_ms,
            cost_estimate=self._estimate_cost(agent_config.model, prompt_tokens, completion_tokens),
            fallback_triggered=False,
        )


    @staticmethod
    def _compact_state(state: dict[str, Any]) -> dict[str, Any]:
        keys = [
            "run_id", "ticker", "run_type", "objective", "current_stage", "stage",
            "task", "allowed_tools", "input_artifact_refs", "evidence_packet_path",
            "relevant_gate_results", "known_limitations", "required_handoff_fields",
            "snapshot_id", "artifacts", "gate_results", "approvals",
            "artifact_refs", "evidence_refs", "errors",
        ]
        return {key: state.get(key) for key in keys}

    @staticmethod
    def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
        in_rate = _INPUT_COST_PER_M.get(model, _DEFAULT_INPUT_COST)
        out_rate = _OUTPUT_COST_PER_M.get(model, _DEFAULT_OUTPUT_COST)
        return (prompt_tokens * in_rate + completion_tokens * out_rate) / 1_000_000


# Backward-compatible public name used by the harness and existing integrations.
# The adapter implementation is provider-selected here, so callers do not need
# coordinated import changes during a provider migration.
OpenAIModelAdapter = AnthropicModelAdapter
