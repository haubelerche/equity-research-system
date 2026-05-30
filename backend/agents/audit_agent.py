from __future__ import annotations

from typing import Any

from backend.harness.state import AgentResult


class AuditAgent:
    """Final agent-level review after deterministic quality and citation gates."""

    role = "AuditAgent"

    def run(self, state: dict[str, Any]) -> AgentResult:
        gate_results = state.get("gate_results") or {}
        blocking = [
            name for name, result in gate_results.items()
            if isinstance(result, dict) and result.get("passed") is False
        ]
        warnings = [f"gate_failed:{name}" for name in blocking]
        return AgentResult(
            status="needs_review" if blocking else "completed",
            payload={
                "ticker": state.get("ticker"),
                "passed": not blocking,
                "blocking_gates": blocking,
            },
            artifact_refs=list(state.get("artifact_refs") or []),
            evidence_refs=list(state.get("evidence_refs") or []),
            confidence=0.65 if blocking else 0.92,
            confidence_breakdown={"deterministic_gate_alignment": 0.65 if blocking else 0.95},
            requires_human=bool(blocking),
            review_reason="; ".join(warnings) if warnings else None,
            warnings=warnings,
        )
