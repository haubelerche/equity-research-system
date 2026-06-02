from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any

from backend.harness.agent_registry import AgentConfig
from backend.harness.state import AgentResult


class OpenAIModelAdapter:
    def validate_environment(self) -> None:
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is required for 5-agent harness execution")
        try:
            import openai  # noqa: F401
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("openai package is required for agent execution") from exc

    def run_agent(
        self,
        agent_config: AgentConfig,
        state: dict[str, Any],
        task: str,
        input_refs: list[str] | None = None,
    ) -> AgentResult:
        self.validate_environment()
        # langfuse.openai is a drop-in replacement that auto-captures model, tokens, and latency.
        # It must be imported after env vars are loaded (load_dotenv is called in the entry scripts).
        from langfuse.openai import OpenAI

        run_id: str = state.get("run_id") or ""
        ticker: str = state.get("ticker") or ""
        # Langfuse trace_id must be a 32 lowercase hex char string.
        # Derive it deterministically from run_id so all generations link to one trace.
        lf_trace_id: str = hashlib.md5(run_id.encode()).hexdigest()  # always 32 hex chars

        started = time.perf_counter()
        client = OpenAI()
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
        response = client.chat.completions.create(
            model=agent_config.model,
            temperature=agent_config.temperature,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": agent_config.prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False, default=str)},
            ],
            timeout=agent_config.timeout_seconds,
            # Langfuse v4 tracing params: name, trace_id, metadata, langfuse_prompt.
            # trace_id must be 32 lowercase hex chars — use md5(run_id) for stable linking.
            name=agent_config.agent_id,
            trace_id=lf_trace_id,
            metadata={
                "ticker": ticker,
                "agent_id": agent_config.agent_id,
                "task": task[:300],
                "stage": state.get("current_stage"),
                "run_type": state.get("run_type"),
            },
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        content = response.choices[0].message.content or "{}"
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
        prompt_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
        completion_tokens = getattr(usage, "completion_tokens", 0) if usage else 0
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
            cost_estimate=self._estimate_cost(prompt_tokens, completion_tokens),
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
    def _estimate_cost(prompt_tokens: int, completion_tokens: int) -> float:
        return ((prompt_tokens * 0.2) + (completion_tokens * 0.8)) / 1_000_000
