from __future__ import annotations

import http.client
import json
import logging
import os
import sys
import time
from typing import Any

from backend.harness.agent_registry import AgentConfig
from backend.harness.state import AgentResult

_log = logging.getLogger("harness.model_adapter")

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


def _transient_exc_types() -> tuple[type[BaseException], ...]:
    """Return the exception types that indicate a transient network error worth retrying."""
    import openai
    types_: list[type[BaseException]] = [http.client.IncompleteRead, ConnectionError]
    for _attr in ("APIConnectionError", "APITimeoutError"):
        _cls = getattr(openai, _attr, None)
        if _cls is not None:
            types_.append(_cls)
    return tuple(types_)


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
        stage = state.get("current_stage") or "?"

        # ── 1. Compact state ────────────────────────────────────────────
        t0 = time.perf_counter()
        state_payload = self._compact_state(state)
        compact_ms = int((time.perf_counter() - t0) * 1000)

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

        # ── 2. Build messages + estimate input size ─────────────────────
        system_msg = agent_config.prompt
        user_msg = json.dumps(user_payload, ensure_ascii=False, default=str)
        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ]
        input_chars = len(system_msg) + len(user_msg)
        est_input_tokens = input_chars // 4  # rough estimate

        max_completion_tokens = _OPENAI_MAX_COMPLETION_TOKENS.get(agent_config.model, 16384)
        _log.info(
            "[%s] LLM_CALL agent=%s model=%s est_input_tokens=%d max_output_tokens=%d "
            "timeout=%ds compact_ms=%d",
            stage, agent_config.agent_id, agent_config.model,
            est_input_tokens, max_completion_tokens,
            agent_config.timeout_seconds, compact_ms,
        )
        sys.stderr.flush()

        # ── 3. Fire the LLM call ───────────────────────────────────────
        create_kwargs: dict[str, Any] = {
            "model": agent_config.model,
            "messages": messages,
            "max_completion_tokens": max_completion_tokens,
            "response_format": {"type": "json_object"},
        }
        if agent_config.model not in _TEMPERATURE_NOT_SUPPORTED:
            create_kwargs["temperature"] = agent_config.temperature
        _transient = _transient_exc_types()
        _fatal_exc: BaseException | None = None  # non-transient or exhausted-transient
        _response = None
        for _attempt in range(3):
            try:
                _response = self._create_completion(client, create_kwargs)
                break  # success — exit retry loop
            except _transient as exc:
                _log.warning(
                    "[%s] transient LLM read error (attempt %d/3): %s: %s",
                    stage, _attempt + 1, type(exc).__name__, exc,
                )
                if _attempt == 2:
                    # All retries exhausted — record and fall to diagnostic path.
                    _fatal_exc = exc
                else:
                    time.sleep(2 * (_attempt + 1))
            except Exception as exc:
                # Non-transient error — record and stop immediately.
                _fatal_exc = exc
                break

        if _fatal_exc is not None:
            call_ms = int((time.perf_counter() - started) * 1000)
            _log.error(
                "[%s] LLM_FAIL agent=%s after %dms: %s: %s",
                stage, agent_config.agent_id, call_ms,
                type(_fatal_exc).__name__, _fatal_exc,
            )
            diagnostic = {
                "provider": self.provider,
                "model": agent_config.model,
                "exception_type": type(_fatal_exc).__name__,
                "exception_message": str(_fatal_exc),
                "failure_stage": "chat_completions_create",
                "agent_id": agent_config.agent_id,
                "task": task,
                "stage": stage,
            }
            raise RuntimeError(
                "agent_llm_call_failed: "
                + json.dumps(diagnostic, ensure_ascii=False, sort_keys=True, default=str)
            ) from _fatal_exc

        response = _response  # type: ignore[assignment]  # guaranteed non-None on success path

        # ── 4. Parse response ──────────────────────────────────────────
        latency_ms = int((time.perf_counter() - started) * 1000)
        usage = response.usage
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0
        _log.info(
            "[%s] LLM_OK agent=%s latency=%dms prompt_tokens=%d completion_tokens=%d "
            "finish_reason=%s",
            stage, agent_config.agent_id, latency_ms,
            prompt_tokens, completion_tokens,
            response.choices[0].finish_reason if response.choices else "?",
        )

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

        # Normalize LLM-returned status to machine states only.
        status = raw.get("status", "completed")
        if status not in {"completed", "failed", "skipped"}:
            status = "completed" if raw.get("payload") else "failed"
        raw_conf = raw.get("confidence", 0.0)
        if isinstance(raw_conf, dict):
            raw_conf = raw_conf.get("overall", raw_conf.get("score", 0.0))
        try:
            confidence = float(raw_conf or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
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

    def _create_completion(self, client, create_kwargs: dict[str, Any]):
        """Single (non-retrying) call to the chat completion API — the retry seam."""
        return client.chat.completions.create(**create_kwargs)

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

    # ── Stage-specific artifact whitelists ──────────────────────────────────
    # Each stage's agent only receives the upstream artifacts it actually needs.
    # Unlisted stages pass artifacts through unfiltered (e.g. PREFLIGHT has none).
    _STAGE_ARTIFACT_WHITELIST: dict[str, set[str]] = {
        "PLAN": set(),  # research_manager needs only ticker/objective, no artifacts
        "INGEST_AND_VALIDATE": {"auto_ingest", "build_facts", "index"},
        "FINANCIAL_ANALYSIS": {"build_facts", "snapshot", "ratios"},
        "ANALYZE": {"build_facts", "snapshot", "ratios"},
        "FORECAST_AND_VALUE": {
            "snapshot", "ratios", "financial_analysis",
            "forecast_model", "valuation", "valuation_read",
        },
        "WRITE_REPORT": {
            "financial_analysis", "forecast_model", "valuation",
            "valuation_read", "market_snapshot", "readiness_review",
        },
        "REVIEW": {
            "report_draft", "final_report_model", "report_assembly_validation",
            "financial_analysis", "valuation", "quality", "critic_review",
        },
    }

    @staticmethod
    def _compact_artifacts_for_stage(stage: str, artifacts: dict[str, Any]) -> dict[str, Any]:
        whitelist = OpenAIModelAdapter._STAGE_ARTIFACT_WHITELIST.get(stage)
        if whitelist is None:
            return artifacts
        filtered = {
            key: OpenAIModelAdapter._compact_artifact_value(key, value)
            for key, value in artifacts.items()
            if key in whitelist
        }
        # Always include a summary of what was omitted so the LLM knows context exists.
        omitted = sorted(set(artifacts) - whitelist)
        if omitted:
            filtered["_omitted_artifact_keys"] = omitted
        return filtered

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
        # Truncate large nested dicts to keep payload bounded.
        if isinstance(value, dict):
            return OpenAIModelAdapter._truncate_large_dict(value, max_chars=30_000)
        return value

    @staticmethod
    def _truncate_large_dict(d: dict[str, Any], max_chars: int = 30_000) -> dict[str, Any]:
        """If a dict's JSON repr exceeds *max_chars*, keep top-level keys but
        replace oversized leaf values with a size summary."""
        raw = json.dumps(d, ensure_ascii=False, default=str)
        if len(raw) <= max_chars:
            return d
        compacted: dict[str, Any] = {}
        for k, v in d.items():
            v_raw = json.dumps(v, ensure_ascii=False, default=str)
            if len(v_raw) > 8_000:
                if isinstance(v, list):
                    compacted[k] = f"[list: {len(v)} items, {len(v_raw)} chars — truncated]"
                elif isinstance(v, dict):
                    compacted[k] = {
                        "_truncated": True,
                        "_keys": sorted(v.keys())[:20],
                        "_chars": len(v_raw),
                    }
                else:
                    compacted[k] = f"[{type(v).__name__}: {len(v_raw)} chars — truncated]"
            else:
                compacted[k] = v
        return compacted

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
