from __future__ import annotations

from typing import Any


def pass_gate(name: str, summary: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"gate": name, "passed": True, "blocking_reasons": [], "summary": summary or {}}


def fail_gate(name: str, reason: str, summary: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"gate": name, "passed": False, "blocking_reasons": [reason], "summary": summary or {}}


def data_quality_gate(build_facts_summary: dict[str, Any]) -> dict[str, Any]:
    if build_facts_summary.get("valuation_gate") != "pass":
        reasons = build_facts_summary.get("blocking_reasons") or ["valuation_gate_not_passed"]
        return {
            "gate": "DATA_QUALITY_GATE",
            "passed": False,
            "blocking_reasons": reasons,
            "summary": build_facts_summary,
        }
    if not build_facts_summary.get("snapshot_id"):
        return fail_gate("DATA_QUALITY_GATE", "snapshot_id_missing", build_facts_summary)
    return pass_gate("DATA_QUALITY_GATE", build_facts_summary)


def valuation_gate(valuation_summary: dict[str, Any]) -> dict[str, Any]:
    required = ["has_fcff", "has_fcfe", "has_blend", "has_sensitivity"]
    missing = [key for key in required if not valuation_summary.get(key)]
    if missing:
        return fail_gate("VALUATION_GATE", f"missing_valuation_components:{','.join(missing)}", valuation_summary)
    if not valuation_summary.get("snapshot_id"):
        return fail_gate("VALUATION_GATE", "valuation_snapshot_id_missing", valuation_summary)
    assumption_gate = valuation_summary.get("assumption_gate") or {}
    if not isinstance(assumption_gate, dict):
        return fail_gate("VALUATION_GATE", "assumption_gate_missing", valuation_summary)
    return pass_gate("VALUATION_GATE", valuation_summary)


def citation_gate(report_summary: dict[str, Any]) -> dict[str, Any]:
    source_gate = report_summary.get("source_tier_gate") or {}
    if source_gate.get("export_decision") == "BLOCKED":
        return fail_gate("CITATION_GATE", "source_tier_gate_blocked", report_summary)
    if report_summary.get("claims_count", 0) > 0 and report_summary.get("citation_count", 0) <= 0:
        return fail_gate("CITATION_GATE", "claims_without_citations", report_summary)
    return pass_gate("CITATION_GATE", report_summary)


def export_gate(state: dict[str, Any], final_approval_required: bool = True) -> dict[str, Any]:
    gate_results = state.get("gate_results") or {}
    failed = [name for name, gate in gate_results.items() if isinstance(gate, dict) and gate.get("passed") is False]
    if failed:
        return fail_gate("EXPORT_GATE", f"upstream_gate_failed:{','.join(failed)}", {"failed": failed})
    if final_approval_required and (state.get("approvals") or {}).get("final_report") != "approved":
        return fail_gate("EXPORT_GATE", "final_human_approval_missing", {})
    audit = (state.get("artifacts") or {}).get("audit_review", {})
    if audit and audit.get("passed") is False:
        return fail_gate("EXPORT_GATE", "audit_review_failed", audit)
    return pass_gate("EXPORT_GATE", {})
