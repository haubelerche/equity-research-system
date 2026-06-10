from __future__ import annotations

import hashlib
import json
import os
import time
from math import ceil
from typing import Any

from backend.harness.agent_registry import AgentConfig
from backend.harness.state import AgentResult

# Pricing per million tokens
_INPUT_COST_PER_M = {
    "claude-haiku-4-5-20251001": 0.80, "claude-sonnet-4-6": 3.00, "claude-opus-4-8": 15.00,
    "gpt-4o": 2.50, "gpt-4o-mini": 0.15, "gpt-4.1": 2.00, "gpt-4.1-mini": 0.40,
}
_OUTPUT_COST_PER_M = {
    "claude-haiku-4-5-20251001": 4.00, "claude-sonnet-4-6": 15.00, "claude-opus-4-8": 75.00,
    "gpt-4o": 10.00, "gpt-4o-mini": 0.60, "gpt-4.1": 8.00, "gpt-4.1-mini": 1.60,
}
_DEFAULT_INPUT_COST = 0.80
_DEFAULT_OUTPUT_COST = 4.00

_OPENAI_MODELS = {"gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "gpt-4-turbo", "gpt-3.5-turbo", "o3-mini"}


def is_openai_model(model: str) -> bool:
    return model in _OPENAI_MODELS or model.startswith("gpt-") or model.startswith("o1-") or model.startswith("o3-")


def create_model_adapter(model: str | None = None):
    """Factory: return the right adapter based on model name."""
    if model and is_openai_model(model):
        return OpenAIModelAdapter()
    return AnthropicModelAdapter()


class AnthropicModelAdapter:
    provider = "anthropic"

    def validate_environment(
        self,
        agent_config: AgentConfig | None = None,
        state: dict[str, Any] | None = None,
        task: str | None = None,
        prompt_diagnostics: dict[str, int] | None = None,
    ) -> None:
        if not os.getenv("ANTHROPIC_API_KEY"):
            exc = RuntimeError("missing required environment variable ANTHROPIC_API_KEY")
            raise self._diagnostic_error(
                failure_stage="environment_validation",
                exc=exc,
                agent_config=agent_config,
                state=state,
                task=task,
                prompt_diagnostics=prompt_diagnostics,
                client_class="Anthropic",
                client_module="anthropic",
            ) from exc
        try:
            import anthropic  # noqa: F401
        except Exception as exc:  # noqa: BLE001
            raise self._diagnostic_error(
                failure_stage="environment_validation",
                exc=exc,
                agent_config=agent_config,
                state=state,
                task=task,
                prompt_diagnostics=prompt_diagnostics,
                client_class="Anthropic",
                client_module="anthropic",
            ) from exc

    def run_agent(
        self,
        agent_config: AgentConfig,
        state: dict[str, Any],
        task: str,
        input_refs: list[str] | None = None,
    ) -> AgentResult:
        run_id: str = state.get("run_id") or ""
        ticker: str = state.get("ticker") or ""
        lf_trace_id: str = hashlib.md5(run_id.encode()).hexdigest()

        started = time.perf_counter()
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
            "max_tokens": 32000,
            "temperature": agent_config.temperature,
            "system": agent_config.prompt,
            "messages": [
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False, default=str)},
            ],
        }
        prompt_diagnostics = self._prompt_diagnostics(kwargs)
        self.validate_environment(agent_config, state, task, prompt_diagnostics)

        Anthropic: Any
        try:
            # Use langfuse.anthropic drop-in if langfuse is configured; otherwise plain anthropic.
            try:
                from langfuse.anthropic import Anthropic
            except Exception:  # noqa: BLE001
                from anthropic import Anthropic
        except Exception as exc:  # noqa: BLE001
            raise self._diagnostic_error(
                failure_stage="client_import",
                exc=exc,
                agent_config=agent_config,
                state=state,
                task=task,
                prompt_diagnostics=prompt_diagnostics,
                client_class="Anthropic",
                client_module="anthropic",
            ) from exc

        client_options = {
            "timeout": agent_config.timeout_seconds,
            "max_retries": self._max_retries(agent_config.retry_policy),
        }
        try:
            client = Anthropic(**client_options)
        except Exception as exc:  # noqa: BLE001
            raise self._diagnostic_error(
                failure_stage="client_init",
                exc=exc,
                agent_config=agent_config,
                state=state,
                task=task,
                prompt_diagnostics=prompt_diagnostics,
                client_class=getattr(Anthropic, "__name__", "Anthropic"),
                client_module=getattr(Anthropic, "__module__", None),
            ) from exc
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

        try:
            # Stream the response: large typed artifacts exceed the non-streaming
            # output budget and risk read timeouts on slow links. Streaming keeps
            # the connection alive and supports the full max_tokens ceiling.
            with client.messages.stream(**kwargs) as stream:
                response = stream.get_final_message()
        except Exception as exc:  # noqa: BLE001
            raise self._diagnostic_error(
                failure_stage="messages_create",
                exc=exc,
                agent_config=agent_config,
                state=state,
                task=task,
                prompt_diagnostics=prompt_diagnostics,
                client=client,
                client_class=getattr(Anthropic, "__name__", "Anthropic"),
                client_module=getattr(Anthropic, "__module__", None),
            ) from exc
        latency_ms = int((time.perf_counter() - started) * 1000)
        content = response.content[0].text if response.content else "{}"
        raw = self._parse_response_json(content)
        if raw is None:
            raw = {
                "status": "needs_review",
                "payload": {"raw_response": content},
                "confidence": 0.0,
                "confidence_breakdown": {"json_validity": 0.0},
                "requires_human": True,
                "review_reason": "model_returned_malformed_json",
                "warnings": ["model_returned_malformed_json"],
            }
        elif "payload" not in raw and ("producer" in raw or "schema_version" in raw):
            artifact_payload = dict(raw)
            raw = {
                "status": artifact_payload.get("status", "completed"),
                "payload": artifact_payload,
                "confidence": artifact_payload.get("confidence", 0.0),
                "confidence_breakdown": artifact_payload.get("confidence_breakdown", {}),
                "requires_human": artifact_payload.get("requires_human", False),
                "review_reason": artifact_payload.get("review_reason"),
                "warnings": artifact_payload.get("warnings", []),
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


    @classmethod
    def _diagnostic_error(
        cls,
        *,
        failure_stage: str,
        exc: BaseException,
        agent_config: AgentConfig | None = None,
        state: dict[str, Any] | None = None,
        task: str | None = None,
        prompt_diagnostics: dict[str, int] | None = None,
        client: Any | None = None,
        client_class: str | None = None,
        client_module: str | None = None,
    ) -> RuntimeError:
        state = state or {}
        client_type = type(client) if client is not None else None
        diagnostic = {
            "provider": cls.provider,
            "model": getattr(agent_config, "model", None),
            "endpoint": cls._client_endpoint(client),
            "client_class": client_class or (client_type.__name__ if client_type else None),
            "client_module": client_module or (client_type.__module__ if client_type else None),
            "timeout_seconds": getattr(agent_config, "timeout_seconds", None),
            "retry_policy": getattr(agent_config, "retry_policy", None),
            "retry_count": cls._max_retries(getattr(agent_config, "retry_policy", None)),
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
            "exception_chain": cls._exception_chain(exc),
            "proxy_configuration": cls._proxy_configuration(),
            "stage": state.get("current_stage") or state.get("stage"),
            "failure_stage": failure_stage,
            "agent_id": getattr(agent_config, "agent_id", None),
            "task": task or state.get("task"),
            **(prompt_diagnostics or cls._prompt_diagnostics_from_config(agent_config, state, task)),
        }
        return RuntimeError(
            "agent_llm_call_failed: "
            + json.dumps(diagnostic, ensure_ascii=False, sort_keys=True, default=str)
        )

    @staticmethod
    def _max_retries(retry_policy: str | None) -> int:
        return {
            None: 0,
            "no_retry": 0,
            "retry_once": 1,
            "retry_twice": 2,
        }.get(retry_policy, 0)

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
    def _client_endpoint(client: Any | None) -> str:
        if client is not None:
            for attribute in ("base_url", "_base_url"):
                value = getattr(client, attribute, None)
                if value:
                    return str(value)
        return os.getenv("ANTHROPIC_BASE_URL") or "https://api.anthropic.com"

    @staticmethod
    def _proxy_configuration() -> dict[str, str]:
        return {
            key: value
            for key in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "NO_PROXY")
            if (value := os.getenv(key))
        }

    @staticmethod
    def _exception_chain(exc: BaseException) -> list[dict[str, str]]:
        chain: list[dict[str, str]] = []
        current: BaseException | None = exc
        seen: set[int] = set()
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            chain.append({"type": type(current).__name__, "message": str(current)})
            current = current.__cause__ or current.__context__
        return chain

    @staticmethod
    def _prompt_diagnostics(kwargs: dict[str, Any]) -> dict[str, int]:
        system_prompt = str(kwargs.get("system") or "")
        message_chars = 0
        for message in kwargs.get("messages") or []:
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if isinstance(content, str):
                message_chars += len(content)
            else:
                message_chars += len(json.dumps(content, ensure_ascii=False, default=str))
        prompt_char_length = len(system_prompt) + message_chars
        return {
            "prompt_char_length": prompt_char_length,
            "system_prompt_char_length": len(system_prompt),
            "user_prompt_char_length": message_chars,
            "prompt_token_estimate": max(1, ceil(prompt_char_length / 4)),
        }

    @staticmethod
    def _prompt_diagnostics_from_config(
        agent_config: AgentConfig | None,
        state: dict[str, Any],
        task: str | None,
    ) -> dict[str, int]:
        system_prompt = getattr(agent_config, "prompt", "") or ""
        user_payload = {
            "task": task or state.get("task"),
            "state": AnthropicModelAdapter._compact_state(state),
        }
        user_prompt = json.dumps(user_payload, ensure_ascii=False, default=str)
        prompt_char_length = len(system_prompt) + len(user_prompt)
        return {
            "prompt_char_length": prompt_char_length,
            "system_prompt_char_length": len(system_prompt),
            "user_prompt_char_length": len(user_prompt),
            "prompt_token_estimate": max(1, ceil(prompt_char_length / 4)),
        }

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
            compacted["input_artifacts"] = AnthropicModelAdapter._compact_artifacts_for_stage(
                stage,
                compacted["input_artifacts"],
            )
        if isinstance(compacted.get("artifacts"), dict):
            compacted["artifacts"] = AnthropicModelAdapter._compact_artifacts_for_stage(
                stage,
                compacted["artifacts"],
            )
        return compacted

    @staticmethod
    def _compact_artifacts_for_stage(stage: str, artifacts: dict[str, Any]) -> dict[str, Any]:
        if stage == "FINANCIAL_ANALYSIS":
            allowed = {"build_facts", "snapshot", "ratios"}
            return {
                key: AnthropicModelAdapter._compact_artifact_value(key, value)
                for key, value in artifacts.items()
                if key in allowed
            }
        return artifacts

    @staticmethod
    def _compact_artifact_value(key: str, value: Any) -> Any:
        if key == "snapshot" and isinstance(value, dict):
            compacted = dict(value)
            compacted["sample_facts"] = [
                AnthropicModelAdapter._compact_fact(row)
                for row in (value.get("sample_facts") or [])
                if isinstance(row, dict)
            ]
            return compacted
        return value

    @staticmethod
    def _compact_fact(row: dict[str, Any]) -> dict[str, Any]:
        fields = (
            "ticker",
            "fiscal_year",
            "fiscal_period",
            "line_item_code",
            "value",
            "unit",
            "currency",
            "source_tier",
            "source_uri",
            "source_title",
            "reconciliation_status",
        )
        return {field: row.get(field) for field in fields if field in row}

    @staticmethod
    def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
        in_rate = _INPUT_COST_PER_M.get(model, _DEFAULT_INPUT_COST)
        out_rate = _OUTPUT_COST_PER_M.get(model, _DEFAULT_OUTPUT_COST)
        return (prompt_tokens * in_rate + completion_tokens * out_rate) / 1_000_000


class OpenAIModelAdapter:
    """Model adapter that uses the OpenAI chat completions API."""

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
        run_id: str = state.get("run_id") or ""
        started = time.perf_counter()

        state_payload = AnthropicModelAdapter._compact_state(state)
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

        self.validate_environment(agent_config, state, task)

        import openai
        client = openai.OpenAI(timeout=agent_config.timeout_seconds)

        messages = [
            {"role": "system", "content": agent_config.prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False, default=str)},
        ]

        try:
            response = client.chat.completions.create(
                model=agent_config.model,
                messages=messages,
                max_tokens=32000,
                temperature=agent_config.temperature,
                response_format={"type": "json_object"},
            )
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
        raw = AnthropicModelAdapter._parse_response_json(content)
        if raw is None:
            raw = {
                "status": "needs_review",
                "payload": {"raw_response": content},
                "confidence": 0.0,
                "confidence_breakdown": {"json_validity": 0.0},
                "requires_human": True,
                "review_reason": "model_returned_malformed_json",
                "warnings": ["model_returned_malformed_json"],
            }
        elif "payload" not in raw and ("producer" in raw or "schema_version" in raw):
            artifact_payload = dict(raw)
            raw = {
                "status": artifact_payload.get("status", "completed"),
                "payload": artifact_payload,
                "confidence": artifact_payload.get("confidence", 0.0),
                "confidence_breakdown": artifact_payload.get("confidence_breakdown", {}),
                "requires_human": artifact_payload.get("requires_human", False),
                "review_reason": artifact_payload.get("review_reason"),
                "warnings": artifact_payload.get("warnings", []),
            }

        usage = response.usage
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0
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
            cost_estimate=AnthropicModelAdapter._estimate_cost(agent_config.model, prompt_tokens, completion_tokens),
            fallback_triggered=False,
        )
