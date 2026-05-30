from __future__ import annotations

from typing import Any

from backend.harness.state import AgentResult


class ResearchAgent:
    """Grounded narrative reviewer over already-created deterministic artifacts."""

    role = "ResearchAgent"

    def run(self, state: dict[str, Any]) -> AgentResult:
        valuation = (state.get("artifacts") or {}).get("valuation", {})
        report = (state.get("artifacts") or {}).get("report", {})
        warnings: list[str] = []

        if not valuation:
            warnings.append("valuation_artifact_missing_for_research_review")
        if not report:
            warnings.append("report_artifact_missing_for_research_review")

        payload = {
            "ticker": state.get("ticker"),
            "review_focus": "grounded narrative consistency",
            "report_path": report.get("report_path") if isinstance(report, dict) else None,
            "valuation_snapshot_id": valuation.get("snapshot_id") if isinstance(valuation, dict) else None,
            "warnings": warnings,
        }
        return AgentResult(
            status="needs_review" if warnings else "completed",
            payload=payload,
            artifact_refs=list(state.get("artifact_refs") or []),
            evidence_refs=list(state.get("evidence_refs") or []),
            confidence=0.78 if warnings else 0.88,
            confidence_breakdown={"artifact_presence": 0.6 if warnings else 0.9},
            requires_human=bool(warnings),
            review_reason="; ".join(warnings) if warnings else None,
            warnings=warnings,
        )
