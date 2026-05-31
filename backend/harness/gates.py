from __future__ import annotations

from typing import Any


def pass_gate(name: str, summary: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"gate": name, "passed": True, "blocking_reasons": [], "summary": summary or {}}


def fail_gate(name: str, reason: str, summary: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"gate": name, "passed": False, "blocking_reasons": [reason], "summary": summary or {}}


def data_quality_gate(build_facts_summary: dict[str, Any]) -> dict[str, Any]:
    blocking_reasons: list[str] = []
    if build_facts_summary.get("valuation_gate") != "pass":
        blocking_reasons.extend(build_facts_summary.get("blocking_reasons") or ["valuation_gate_not_passed"])
    if not build_facts_summary.get("snapshot_id"):
        blocking_reasons.append("snapshot_id_missing")
    periods = build_facts_summary.get("periods_available") or []
    if periods and any(not str(period).endswith("FY") for period in periods):
        blocking_reasons.append("invalid_period_scope")
    for gate_key in ("coverage_gate", "core_keys_gate", "source_validation_gate"):
        if build_facts_summary.get(gate_key) == "fail":
            blocking_reasons.append(f"{gate_key}_failed")
    if build_facts_summary.get("source_tier_coverage_status") == "fail":
        blocking_reasons.append("source_tier_coverage_failed")
    if build_facts_summary.get("reconciliation_status") in {"fail", "manual_review"}:
        blocking_reasons.append("reconciliation_requires_review")
    if blocking_reasons:
        return {
            "gate": "DATA_QUALITY_GATE",
            "passed": False,
            "blocking_reasons": sorted(set(blocking_reasons)),
            "summary": build_facts_summary,
        }
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


def export_gate(state: dict[str, Any], final_approval_required: bool = True) -> dict[str, Any]:
    gate_results = state.get("gate_results") or {}
    failed = [name for name, gate in gate_results.items() if isinstance(gate, dict) and gate.get("passed") is False]
    if failed:
        return fail_gate("EXPORT_GATE", f"upstream_gate_failed:{','.join(failed)}", {"failed": failed})
    if final_approval_required and (state.get("approvals") or {}).get("final_report") != "approved":
        return fail_gate("EXPORT_GATE", "final_human_approval_missing", {})
    evaluation = state.get("evaluation_results") or (state.get("artifacts") or {}).get("quality") or {}
    if evaluation.get("overall_status") in {"FAIL", "failed", "fail"}:
        return fail_gate("EXPORT_GATE", "quality_evaluation_failed", evaluation)
    valuation = state.get("valuation_outputs") or (state.get("artifacts") or {}).get("valuation") or {}
    report = state.get("draft_report") or (state.get("artifacts") or {}).get("report") or {}
    if valuation and report and valuation.get("snapshot_id") != report.get("snapshot_id"):
        return fail_gate("EXPORT_GATE", "report_not_linked_to_valuation_snapshot", {"valuation": valuation, "report": report})
    if final_approval_required and valuation and not (state.get("artifacts") or {}).get("valuation_lock"):
        return fail_gate("EXPORT_GATE", "approved_valuation_lock_missing", {})
    audit = (state.get("artifacts") or {}).get("audit_review", {})
    if audit and audit.get("passed") is False:
        return fail_gate("EXPORT_GATE", "audit_review_failed", audit)
    return pass_gate("EXPORT_GATE", {})


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
        return {
            "gate": "OCR_EXPORT_GATE",
            "passed": False,
            "blocking_reasons": blocking_reasons,
            "summary": {
                "total_candidates": total,
                "promoted": promoted,
                "blocked": blocked,
                "blocking_facts": blocking_facts,
                "action": "inspect reconciliation report, manually approve or correct candidate facts, rerun promotion",
                "report_mode": "final",
            },
        }

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
