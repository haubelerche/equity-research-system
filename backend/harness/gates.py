from __future__ import annotations

import re
from typing import Any

_FY_PATTERN = re.compile(r"^20\d{2}FY$")
_METRIC_REF_PATTERN = re.compile(r"\b[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+\b")
_PERIOD_REF_PATTERN = re.compile(r"\b20\d{2}(?:FY|A|F)?\b")


def _issue_id(gate_name: str, reason: str) -> str:
    prefix = re.sub(r"[^A-Z0-9]+", "_", gate_name.upper()).strip("_")
    suffix = re.sub(r"[^A-Z0-9]+", "_", reason.upper()).strip("_")[:64]
    return f"{prefix}:{suffix or 'FAILED'}"


def _gate_result(
    name: str,
    passed: bool,
    blocking_reasons: list[str] | None = None,
    summary: dict[str, Any] | None = None,
    severity: str | None = None,
) -> dict[str, Any]:
    reasons = blocking_reasons or []
    result_severity = severity or ("none" if passed else "critical")
    return {
        "gate": name,
        "passed": passed,
        "status": "pass" if passed else "fail",
        "severity": result_severity,
        "blocking_reasons": reasons,
        "issues": [
            {
                "issue_id": _issue_id(name, reason),
                "severity": result_severity,
                "message": reason,
                "blocking": True,
            }
            for reason in reasons
        ],
        "summary": summary or {},
    }


def pass_gate(name: str, summary: dict[str, Any] | None = None) -> dict[str, Any]:
    return _gate_result(name, True, [], summary, severity="none")


def fail_gate(
    name: str,
    reason: str,
    summary: dict[str, Any] | None = None,
    severity: str = "critical",
) -> dict[str, Any]:
    return _gate_result(name, False, [reason], summary, severity=severity)


def data_quality_gate(build_facts_summary: dict[str, Any]) -> dict[str, Any]:
    blocking_reasons: list[str] = []
    if build_facts_summary.get("valuation_gate") != "pass":
        blocking_reasons.extend(build_facts_summary.get("blocking_reasons") or ["valuation_gate_not_passed"])
    if not build_facts_summary.get("snapshot_id"):
        blocking_reasons.append("snapshot_id_missing")
    periods = build_facts_summary.get("periods_available") or []
    if periods and any(not _FY_PATTERN.match(str(period)) for period in periods):
        blocking_reasons.append("invalid_period_scope")
    for gate_key in ("coverage_gate", "core_keys_gate", "source_validation_gate"):
        if build_facts_summary.get(gate_key) == "fail":
            blocking_reasons.append(f"{gate_key}_failed")
    if build_facts_summary.get("source_tier_coverage_status") == "fail":
        blocking_reasons.append("source_tier_coverage_failed")
    if build_facts_summary.get("reconciliation_status") in {"fail", "manual_review"}:
        blocking_reasons.append("reconciliation_requires_review")
    if blocking_reasons:
        return _gate_result("DATA_QUALITY_GATE", False, sorted(set(blocking_reasons)), build_facts_summary)
    return pass_gate("DATA_QUALITY_GATE", build_facts_summary)


def valuation_gate(valuation_summary: dict[str, Any]) -> dict[str, Any]:
    required = ["has_fcff", "has_fcfe", "has_blend", "has_sensitivity"]
    required_metadata = ["formula_version", "assumption_version", "unit_policy", "currency", "period_scope"]
    missing = [key for key in required if not valuation_summary.get(key)]
    missing.extend([key for key in required_metadata if not valuation_summary.get(key)])
    if not valuation_summary.get("assumptions"):
        missing.append("assumptions")
    if not valuation_summary.get("sensitivity_summary"):
        missing.append("sensitivity_summary")
    if not valuation_summary.get("valuation_methods"):
        missing.append("valuation_methods")
    if missing:
        return fail_gate("VALUATION_GATE", f"missing_valuation_components:{','.join(missing)}", valuation_summary)
    if not valuation_summary.get("snapshot_id"):
        return fail_gate("VALUATION_GATE", "valuation_snapshot_id_missing", valuation_summary)
    assumption_gate = valuation_summary.get("assumption_gate") or {}
    if not isinstance(assumption_gate, dict):
        return fail_gate("VALUATION_GATE", "assumption_gate_missing", valuation_summary)
    return pass_gate("VALUATION_GATE", valuation_summary)


def financial_analyst_gate(financial_summary: dict[str, Any]) -> dict[str, Any]:
    if financial_summary.get("requires_human"):
        return fail_gate("FINANCIAL_ANALYST_GATE", financial_summary.get("review_reason") or "financial_analyst_requires_review", financial_summary)
    if financial_summary.get("status") in {"failed", "needs_review"}:
        return fail_gate("FINANCIAL_ANALYST_GATE", "financial_analyst_failed", financial_summary)
    import json
    text = json.dumps(
        {
            "payload": financial_summary.get("payload", {}),
            "output_summary": financial_summary.get("output_summary", {}),
            "warnings": financial_summary.get("warnings", []),
        },
        ensure_ascii=False,
        default=str,
    )
    metric_refs = set(_METRIC_REF_PATTERN.findall(text))
    period_refs = set(_PERIOD_REF_PATTERN.findall(text))
    input_refs = set(financial_summary.get("input_summary", {}).get("input_refs") or [])
    financial_summary.setdefault("effectiveness", {})
    financial_summary["effectiveness"].update(
        {
            "metric_reference_count": len(metric_refs),
            "period_reference_count": len(period_refs),
            "input_ref_count": len(input_refs),
        }
    )
    if not metric_refs or not period_refs:
        return fail_gate(
            "FINANCIAL_ANALYST_GATE",
            "financial_analyst_missing_traceable_metric_or_period_refs",
            financial_summary,
        )
    if not any("fact" in ref or "snapshot" in ref for ref in input_refs) or not any("ratio" in ref for ref in input_refs):
        return fail_gate(
            "FINANCIAL_ANALYST_GATE",
            "financial_analyst_missing_snapshot_or_ratio_artifact_ref",
            financial_summary,
        )
    return pass_gate("FINANCIAL_ANALYST_GATE", financial_summary)


def citation_gate(report_summary: dict[str, Any]) -> dict[str, Any]:
    source_gate = report_summary.get("source_tier_gate") or {}
    if source_gate.get("export_decision") == "BLOCKED" or source_gate.get("blocking_count", 0) > 0:
        return fail_gate("CITATION_GATE", "source_tier_gate_blocked", report_summary)
    if report_summary.get("tier3_only_material_count", 0) > 0:
        return fail_gate("CITATION_GATE", "tier3_only_material_claims", report_summary)
    if report_summary.get("unsupported_numeric_claims_count", 0) > 0:
        return fail_gate("CITATION_GATE", "unsupported_numeric_claims", report_summary)
    if report_summary.get("claims_count", 0) > 0 and report_summary.get("citation_count", 0) <= 0:
        return fail_gate("CITATION_GATE", "claims_without_citations", report_summary)
    return pass_gate("CITATION_GATE", report_summary)


def tool_permission_gate(trace: list[dict[str, Any]]) -> dict[str, Any]:
    tool_calls = [entry for entry in trace if entry.get("kind") == "tool_call"]
    missing = [
        entry.get("tool_name") or "unknown_tool"
        for entry in tool_calls
        if not (entry.get("gate_inputs") or {}).get("tool_permission")
    ]
    if missing:
        return _gate_result("TOOL_PERMISSION_GATE", False, [f"tool_permission_missing:{','.join(sorted(set(missing)))}"], {"tool_calls": len(tool_calls)})
    return pass_gate("TOOL_PERMISSION_GATE", {"tool_calls": len(tool_calls)})


def artifact_manifest_gate(state: dict[str, Any]) -> dict[str, Any]:
    refs = state.get("artifact_refs") or []
    missing_paths = [
        str(ref.get("artifact_id") or ref.get("section_key") or "unknown_artifact")
        for ref in refs
        if isinstance(ref, dict)
        and ref.get("artifact_type") not in {"agent_message"}
        and not ref.get("storage_path")
        and ref.get("section_key") in {"facts", "index", "ratios", "valuation", "report", "full_report_draft", "evidence_packet"}
    ]
    if missing_paths:
        return _gate_result("ARTIFACT_MANIFEST_GATE", False, [f"artifact_storage_path_missing:{','.join(sorted(set(missing_paths)))}"], {"artifact_refs": len(refs)})
    return pass_gate("ARTIFACT_MANIFEST_GATE", {"artifact_refs": len(refs)})


def formula_trace_gate(valuation_summary: dict[str, Any]) -> dict[str, Any]:
    if not valuation_summary:
        return pass_gate("FORMULA_TRACE_GATE", {"valuation_present": False})
    traces = valuation_summary.get("formula_traces") or []
    if not traces or valuation_summary.get("formula_trace_status") == "missing":
        return fail_gate("FORMULA_TRACE_GATE", "missing_formula_trace", valuation_summary)
    invalid = [
        str(trace.get("trace_id") or trace.get("formula_id") or "unknown_trace")
        for trace in traces
        if not isinstance(trace, dict)
        or not trace.get("formula_id")
        or not trace.get("formula_version")
        or not trace.get("calculation_steps")
    ]
    if invalid:
        return _gate_result("FORMULA_TRACE_GATE", False, [f"invalid_formula_trace:{','.join(invalid[:10])}"], {"trace_count": len(traces)})
    return pass_gate("FORMULA_TRACE_GATE", {"trace_count": len(traces)})


def evidence_packet_gate(state: dict[str, Any]) -> dict[str, Any]:
    refs = state.get("artifact_refs") or []
    evidence_refs = [
        ref for ref in refs
        if isinstance(ref, dict) and ref.get("section_key") == "evidence_packet" and ref.get("storage_path")
    ]
    if not evidence_refs:
        return fail_gate("EVIDENCE_PACKET_GATE", "evidence_packet_missing", {"artifact_refs": len(refs)})
    valuation = state.get("valuation_outputs") or (state.get("artifacts") or {}).get("valuation") or {}
    if valuation and not valuation.get("formula_traces"):
        return fail_gate("EVIDENCE_PACKET_GATE", "evidence_packet_missing_formula_traces", valuation)
    return pass_gate("EVIDENCE_PACKET_GATE", {"evidence_packet_path": evidence_refs[-1].get("storage_path")})


def agent_handoff_gate(state: dict[str, Any]) -> dict[str, Any]:
    handoffs = (state.get("artifacts") or {}).get("agent_handoffs") or []
    expected_agents = {"supervisor", "data_retrieval", "financial_analyst", "valuation", "report_writer_critic"}
    seen = {handoff.get("agent_id") for handoff in handoffs if isinstance(handoff, dict)}
    missing = sorted(expected_agents - seen)
    if missing:
        return _gate_result("AGENT_HANDOFF_GATE", False, [f"agent_handoff_missing:{','.join(missing)}"], {"handoff_count": len(handoffs)})
    invalid = [
        str(handoff.get("agent_id") or "unknown_agent")
        for handoff in handoffs
        if isinstance(handoff, dict) and not handoff.get("handoff_hash")
    ]
    if invalid:
        return _gate_result("AGENT_HANDOFF_GATE", False, [f"agent_handoff_hash_missing:{','.join(invalid)}"], {"handoff_count": len(handoffs)})
    return pass_gate("AGENT_HANDOFF_GATE", {"handoff_count": len(handoffs)})


def approval_path_gate(state: dict[str, Any], final_approval_required: bool = True) -> dict[str, Any]:
    if not final_approval_required:
        return pass_gate("APPROVAL_PATH_GATE", {"final_approval_required": False})
    approvals = state.get("approvals") or {}
    decisions = state.get("human_review_decisions") or {}
    final_decision = decisions.get("final_report") or {}
    if approvals.get("final_report") != "approved" or final_decision.get("decision") != "approved":
        return fail_gate("APPROVAL_PATH_GATE", "final_approval_not_recorded_by_runner", {"approvals": approvals, "human_review_decisions": decisions})
    return pass_gate("APPROVAL_PATH_GATE", {"final_approval_required": True, "reviewer": final_decision.get("reviewer")})


def workflow_export_gate(state: dict[str, Any], final_approval_required: bool = True) -> dict[str, Any]:
    gate_results = state.get("gate_results") or {}
    blocking_reasons: list[str] = []
    required_gates = {
        "TOOL_PERMISSION_GATE",
        "ARTIFACT_MANIFEST_GATE",
        "FORMULA_TRACE_GATE",
        "EVIDENCE_PACKET_GATE",
        "AGENT_HANDOFF_GATE",
    }
    if final_approval_required:
        required_gates.add("APPROVAL_PATH_GATE")
    missing_required = sorted(name for name in required_gates if name not in gate_results)
    if missing_required:
        blocking_reasons.append(f"required_harness_gate_missing:{','.join(missing_required)}")
    failed = [name for name, gate in gate_results.items() if isinstance(gate, dict) and gate.get("passed") is False]
    if failed:
        blocking_reasons.append(f"upstream_gate_failed:{','.join(failed)}")
    if final_approval_required and (state.get("approvals") or {}).get("final_report") != "approved":
        blocking_reasons.append("final_human_approval_missing")
    evaluation = state.get("evaluation_results") or (state.get("artifacts") or {}).get("quality") or {}
    if evaluation.get("overall_status") in {"FAIL", "failed", "fail"}:
        blocking_reasons.append("quality_evaluation_failed")
    valuation = state.get("valuation_outputs") or (state.get("artifacts") or {}).get("valuation") or {}
    report = state.get("draft_report") or (state.get("artifacts") or {}).get("report") or {}
    blocking_reasons.extend(_report_export_blockers(report))
    blocking_reasons.extend(_valuation_export_blockers(valuation))
    blocking_reasons.extend(_evaluation_export_blockers(evaluation))
    if valuation and report and valuation.get("snapshot_id") != report.get("snapshot_id"):
        blocking_reasons.append("report_not_linked_to_valuation_snapshot")
    if final_approval_required and valuation and not (state.get("artifacts") or {}).get("valuation_lock"):
        blocking_reasons.append("approved_valuation_lock_missing")
    audit = (state.get("artifacts") or {}).get("audit_review", {})
    if audit and audit.get("passed") is False:
        blocking_reasons.append("audit_review_failed")
    if blocking_reasons:
        return _gate_result(
            "EXPORT_GATE",
            False,
            sorted(set(blocking_reasons)),
            {
                "missing_required_gates": missing_required,
                "failed_gates": failed,
                "valuation": valuation,
                "report": report,
                "evaluation": evaluation,
            },
        )
    return pass_gate("EXPORT_GATE", {})


def _positive(summary: dict[str, Any], *keys: str) -> bool:
    return any(bool(summary.get(key, 0)) for key in keys)


def _report_export_blockers(report: dict[str, Any]) -> list[str]:
    if not report:
        return []
    blockers: list[str] = []
    source_gate = report.get("source_tier_gate") or {}
    if report.get("export_blocked") is True:
        blockers.append("report_generation_marked_export_blocked")
    if source_gate.get("export_decision") == "BLOCKED" or source_gate.get("blocking_count", 0) > 0:
        blockers.append("source_tier_gate_blocked")
    if _positive(report, "tier3_only_material_count"):
        blockers.append("tier3_only_material_fact")
    if _positive(report, "unsupported_numeric_claims_count", "missing_source_trace_count"):
        blockers.append("missing_source_trace_for_material_claim")
    if _positive(report, "unresolved_discrepancy_count", "major_discrepancy_count"):
        blockers.append("unresolved_major_source_discrepancy")
    if _positive(report, "generic_citation_count"):
        blockers.append("generic_citation_only")
    if _positive(report, "missing_formula_trace_count"):
        blockers.append("missing_formula_trace")
    if _positive(report, "missing_forecast_driver_count"):
        blockers.append("missing_forecast_driver")
    return sorted(set(blockers))


def _valuation_export_blockers(valuation: dict[str, Any]) -> list[str]:
    if not valuation:
        return []
    blockers: list[str] = []
    if _positive(valuation, "missing_formula_trace_count") or valuation.get("formula_trace_status") == "missing":
        blockers.append("missing_formula_trace")
    if _positive(valuation, "na_input_count", "unresolved_na_count") or valuation.get("has_na_inputs") is True:
        blockers.append("unresolved_na_in_valuation")
    if valuation.get("debt_forecast_missing") is True:
        blockers.append("missing_debt_forecast_when_required")
    return sorted(set(blockers))


def _evaluation_export_blockers(evaluation: dict[str, Any]) -> list[str]:
    if not evaluation:
        return []
    if evaluation.get("llm_only_pass") is True:
        return ["llm_only_evaluation_pass"]
    return []


def ocr_export_gate(
    candidate_facts: list[Any],  # list[CandidateFact] — use Any to avoid circular import
    report_mode: str = "final",  # "draft" | "final"
) -> dict[str, Any]:
    """Gate that blocks final report export if any quantitative OCR facts are unresolved.

    In "draft" mode: always passes (warnings may be present in summary).
    In "final" mode: fails if any CandidateFact has promotion_status == "blocked".

    Args:
        candidate_facts: List of CandidateFact objects (use Any to avoid circular import).
        report_mode: "draft" or "final". Only "final" mode can fail this gate.

    Returns:
        Gate result dict with structure:
            {
                "gate": "OCR_EXPORT_GATE",
                "passed": bool,
                "blocking_reasons": list[str],
                "summary": {
                    "total_candidates": int,
                    "promoted": int,
                    "blocked": int,
                    "blocking_facts": list[dict],
                    "action": str,
                }
            }
    """
    total = len(candidate_facts) if candidate_facts else 0
    promoted = sum(1 for f in candidate_facts if getattr(f, "promotion_status", None) == "promoted")
    blocked = sum(1 for f in candidate_facts if getattr(f, "promotion_status", None) == "blocked")

    # Build blocking_facts with detailed reasons
    blocking_facts = []
    blocking_reasons = []

    if report_mode == "draft":
        # Draft mode always passes, even if facts are blocked
        return pass_gate(
            "OCR_EXPORT_GATE",
            {
                "total_candidates": total,
                "promoted": promoted,
                "blocked": blocked,
                "blocking_facts": [],
                "action": "draft mode — unresolved candidate facts allowed",
                "report_mode": "draft",
            },
        )

    # Final mode: check for blocked facts
    for fact in candidate_facts:
        if getattr(fact, "promotion_status", None) == "blocked":
            metric_id = getattr(fact, "metric_id", "unknown")
            reconciliation_status = getattr(fact, "reconciliation_status", "not_checked")
            validation_status = getattr(fact, "validation_status", "pending")
            warnings = getattr(fact, "warnings", [])

            # Determine the blocking reason
            if reconciliation_status == "conflicted":
                reason = "OCR candidate conflicted with secondary source"
            elif validation_status == "failed":
                # Use first warning if available, otherwise generic message
                first_warning = warnings[0] if warnings else "validation failed"
                reason = f"validation_failed: {first_warning}"
            elif reconciliation_status == "not_checked":
                reason = "reconciliation_not_run"
            else:
                reason = "promotion_blocked"

            blocking_fact_entry = {
                "metric_id": metric_id,
                "reason": reason,
            }
            blocking_facts.append(blocking_fact_entry)
            blocking_reasons.append(f"{metric_id}:{reason}")

    # If any facts are blocked in final mode, fail the gate
    if blocking_reasons:
        return _gate_result(
            "OCR_EXPORT_GATE",
            False,
            blocking_reasons,
            {
                "total_candidates": total,
                "promoted": promoted,
                "blocked": blocked,
                "blocking_facts": blocking_facts,
                "action": "inspect reconciliation report, manually approve or correct candidate facts, rerun promotion",
                "report_mode": "final",
            },
        )

    # Final mode with no blocked facts: pass
    return pass_gate(
        "OCR_EXPORT_GATE",
        {
            "total_candidates": total,
            "promoted": promoted,
            "blocked": blocked,
            "blocking_facts": [],
            "action": "all candidate facts resolved",
            "report_mode": "final",
        },
    )
