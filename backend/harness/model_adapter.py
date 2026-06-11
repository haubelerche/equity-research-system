from __future__ import annotations

import json
import os
import time
from typing import Any

from backend.harness.agent_registry import AgentConfig
from backend.harness.state import AgentResult

# ── Production model constants ───────────────────────────────────────────────
MAIN_MODEL = "gpt-5-mini"
CHEAP_MODEL = "gpt-5-nano"
PRODUCTION_MODELS = {MAIN_MODEL, CHEAP_MODEL}

_LIGHTWEIGHT_TASK_TYPES = frozenset({
    "route", "classify", "extract_json", "detect_ticker",
    "detect_period", "detect_unit", "normalize_format",
})

_INPUT_COST_PER_M = {MAIN_MODEL: 0.75, CHEAP_MODEL: 0.20}
_OUTPUT_COST_PER_M = {MAIN_MODEL: 4.50, CHEAP_MODEL: 1.25}

_OPENAI_MAX_COMPLETION_TOKENS = {MAIN_MODEL: 32768, CHEAP_MODEL: 16384}
_TEMPERATURE_NOT_SUPPORTED = frozenset({MAIN_MODEL, CHEAP_MODEL})


def select_model_for_task(task_type: str) -> str:
    """Return the production model appropriate for *task_type*."""
    if task_type in _LIGHTWEIGHT_TASK_TYPES:
        return CHEAP_MODEL
    return MAIN_MODEL


def validate_production_model(model: str) -> None:
    """Raise ValueError if *model* is not in the production allow-list."""
    if model not in PRODUCTION_MODELS:
        raise ValueError(
            f"Model {model!r} is not allowed in production. "
            f"Use one of: {', '.join(sorted(PRODUCTION_MODELS))}"
        )


def create_model_adapter(model: str | None = None):
    """Factory: return the OpenAI adapter. Validates production model."""
    resolved = model or MAIN_MODEL
    validate_production_model(resolved)
    return OpenAIModelAdapter()


class OpenAIModelAdapter:
    """Production model adapter — OpenAI chat completions only."""

    provider = "openai"

    def validate_environment(
        self,
        agent_config: AgentConfig | None = None,
        state: dict[str, Any] | None = None,
        task: str | None = None,
        prompt_diagnostics: dict[str, int] | None = None,
    ) -> None:
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("missing required environment variable OPENAI_API_KEY")
        try:
            import openai  # noqa: F401
        except ImportError as exc:
            raise RuntimeError("openai package not installed — pip install openai") from exc

    def run_agent(
        self,
        agent_config: AgentConfig,
        state: dict[str, Any],
        task: str,
        input_refs: list[str] | None = None,
    ) -> AgentResult:
        validate_production_model(agent_config.model)
        started = time.perf_counter()

        state_payload = self._compact_state(state)
        user_payload = {
            "task": task,
            "input_refs": input_refs or [],
            "state": state_payload,
            "required_output": {
                "status": "completed|failed",
                "payload": {},
                "confidence": 0.0,
                "confidence_breakdown": {},
                "warnings": [],
                "next_action": None,
            },
        }

        self.validate_environment(agent_config, state, task)

        import openai
        client = openai.OpenAI(timeout=agent_config.timeout_seconds)

        messages = [
            {"role": "system", "content": agent_config.prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False, default=str)},
        ]

        max_completion_tokens = _OPENAI_MAX_COMPLETION_TOKENS.get(agent_config.model, 16384)
        create_kwargs: dict[str, Any] = {
            "model": agent_config.model,
            "messages": messages,
            "max_completion_tokens": max_completion_tokens,
            "response_format": {"type": "json_object"},
        }
        if agent_config.model not in _TEMPERATURE_NOT_SUPPORTED:
            create_kwargs["temperature"] = agent_config.temperature
        try:
            response = client.chat.completions.create(**create_kwargs)
        except Exception as exc:
            diagnostic = {
                "provider": self.provider,
                "model": agent_config.model,
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
                "failure_stage": "chat_completions_create",
                "agent_id": agent_config.agent_id,
                "task": task,
                "stage": state.get("current_stage"),
            }
            raise RuntimeError(
                "agent_llm_call_failed: "
                + json.dumps(diagnostic, ensure_ascii=False, sort_keys=True, default=str)
            ) from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        content = response.choices[0].message.content or "{}"
        raw = self._parse_response_json(content)
        if raw is None:
            raw = {
                "status": "failed",
                "payload": {"raw_response": content},
                "confidence": 0.0,
                "confidence_breakdown": {"json_validity": 0.0},
                "blocking_reason": "model_returned_malformed_json",
                "warnings": ["model_returned_malformed_json"],
            }
        elif "payload" not in raw and ("producer" in raw or "schema_version" in raw):
            artifact_payload = dict(raw)
            raw = {
                "status": artifact_payload.get("status", "completed"),
                "payload": artifact_payload,
                "confidence": artifact_payload.get("confidence", 0.0),
                "confidence_breakdown": artifact_payload.get("confidence_breakdown", {}),
                "warnings": artifact_payload.get("warnings", []),
            }

        usage = response.usage
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0
        # Normalize LLM-returned status to machine states only.
        status = raw.get("status", "completed")
        if status not in {"completed", "failed", "skipped"}:
            status = "completed" if raw.get("payload") else "failed"
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
            blocking_reason=raw.get("blocking_reason"),
            warnings=raw.get("warnings", []),
            sources_used=raw.get("sources_used", []),
            latency_ms=latency_ms,
            cost_estimate=self._estimate_cost(agent_config.model, prompt_tokens, completion_tokens),
            fallback_triggered=False,
        )

    @staticmethod
    def _parse_response_json(content: str) -> dict[str, Any] | None:
        text = content.strip()
        if text.startswith("```"):
            first_newline = text.find("\n")
            if first_newline >= 0:
                text = text[first_newline + 1 :]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    @staticmethod
    def _compact_state(state: dict[str, Any]) -> dict[str, Any]:
        keys = [
            "run_id", "ticker", "run_type", "objective", "current_stage", "stage",
            "task", "allowed_tools", "input_artifact_refs", "input_artifacts", "evidence_packet_path",
            "relevant_gate_results", "known_limitations",
            "snapshot_id", "artifacts", "gate_results", "approvals",
            "artifact_refs", "evidence_refs", "errors",
        ]
        compacted = {key: state.get(key) for key in keys}
        stage = str(state.get("current_stage") or state.get("stage") or "")
        if isinstance(compacted.get("input_artifacts"), dict):
            compacted["input_artifacts"] = OpenAIModelAdapter._compact_artifacts_for_stage(
                stage,
                compacted["input_artifacts"],
            )
        if isinstance(compacted.get("artifacts"), dict):
            compacted["artifacts"] = OpenAIModelAdapter._compact_artifacts_for_stage(
                stage,
                compacted["artifacts"],
            )
        return compacted

    @staticmethod
    def _compact_artifacts_for_stage(stage: str, artifacts: dict[str, Any]) -> dict[str, Any]:
        if stage == "FINANCIAL_ANALYSIS":
            allowed = {"build_facts", "snapshot", "ratios"}
            return {
                key: OpenAIModelAdapter._compact_artifact_value(key, value)
                for key, value in artifacts.items()
                if key in allowed
            }
        return artifacts

    @staticmethod
    def _compact_artifact_value(key: str, value: Any) -> Any:
        if key == "snapshot" and isinstance(value, dict):
            compacted = dict(value)
            compacted["sample_facts"] = [
                OpenAIModelAdapter._compact_fact(row)
                for row in (value.get("sample_facts") or [])
                if isinstance(row, dict)
            ]
            return compacted
        return value

    @staticmethod
    def _compact_fact(row: dict[str, Any]) -> dict[str, Any]:
        fields = (
            "ticker", "fiscal_year", "fiscal_period", "line_item_code",
            "value", "unit", "currency", "source_tier", "source_uri",
            "source_title", "reconciliation_status",
        )
        return {field: row.get(field) for field in fields if field in row}

    @staticmethod
    def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
        in_rate = _INPUT_COST_PER_M.get(model, 0.75)
        out_rate = _OUTPUT_COST_PER_M.get(model, 4.50)
        return (prompt_tokens * in_rate + completion_tokens * out_rate) / 1_000_000
