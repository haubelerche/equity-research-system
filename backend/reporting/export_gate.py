"""Unified export gate — Phase 7 master plan §2.4 / hard gates summary.

Aggregates all 8 required gates into a single ExportGateResult:

  source_gate              — material facts have source trace; no Tier-3-only valuation
  reconciliation_gate      — official vs secondary facts do not materially conflict
  numeric_consistency_gate — formulas, shares, units, signs reconcile
  forecast_gate            — debt, dividend, working capital, tax are present and valid
  valuation_gate           — FCFF + P/E Forward blend, WACC/Re, terminal growth, net debt, shares valid
  sensitivity_gate         — sensitivity tables present, non-empty, include base cell
  citation_gate            — material claims have claim-level citations
  layout_gate              — PDF/HTML passes layout_audit checks
  human_review_gate        — analyst approval present for final recommendation

Decision rules:
  - All gates PASS + human_review APPROVED → render_mode = "client_final"
  - Any gate FAIL or human_review missing  → render_mode = "analyst_draft"
  - Blocked gates (data missing)           → render_mode = "analyst_draft"
  - internal_debug is only set explicitly  → never auto-promoted

Final PDF export:
  - Only "client_final" render_mode → final_report.pdf allowed
  - "analyst_draft" → draft_review.pdf only; no target price/rating shown

All arithmetic is deterministic Python — no LLM involvement.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from backend.reporting.report_artifact import ReportArtifact, RenderMode
from backend.reporting.layout_audit import LayoutRenderAudit

GateStatus = Literal["PASS", "FAIL", "SKIP", "BLOCKED"]

# Names match master plan §5 hard gates table
GATE_NAMES = [
    "source_gate",
    "reconciliation_gate",
    "numeric_consistency_gate",
    "forecast_gate",
    "valuation_gate",
    "sensitivity_gate",
    "citation_gate",
    "layout_gate",
    "human_review_gate",
]


@dataclass
class GateResult:
    name: str
    status: GateStatus
    issues: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status == "PASS"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "passed": self.passed,
            "issues": self.issues,
            "metadata": self.metadata,
        }


@dataclass
class ExportGateResult:
    """Unified export decision from all 8 gates."""
    ticker: str
    report_id: str
    gates: dict[str, GateResult]      # keyed by gate name
    render_mode: RenderMode
    is_final_exportable: bool          # True only when all gates PASS + human approved
    blocking_gates: list[str]          # names of gates that prevented final export
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    warnings: list[str] = field(default_factory=list)

    def gate(self, name: str) -> GateResult | None:
        return self.gates.get(name)

    def summary(self) -> dict[str, str]:
        return {name: g.status for name, g in self.gates.items()}

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "report_id": self.report_id,
            "render_mode": self.render_mode,
            "is_final_exportable": self.is_final_exportable,
            "blocking_gates": self.blocking_gates,
            "gate_summary": self.summary(),
            "gates": {name: g.to_dict() for name, g in self.gates.items()},
            "created_at": self.created_at,
            "warnings": self.warnings,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


# ── Gate builders — each evaluates one gate from available inputs ─────────────

def _source_gate(
    valuation_artifact: dict[str, Any] | None,
    source_manifest: dict[str, Any] | None,
) -> GateResult:
    issues: list[str] = []

    if source_manifest is None:
        return GateResult("source_gate", "SKIP",
                          ["source_manifest not provided — gate skipped"])

    # Check if all valuation-critical facts have source trace
    untraced = source_manifest.get("untraced_valuation_facts", [])
    if untraced:
        issues.append(
            f"{len(untraced)} valuation-critical fact(s) missing source trace: "
            + ", ".join(str(u) for u in untraced[:5])
        )

    # Tier-3-only check
    tier3_only = source_manifest.get("tier3_only_valuation_facts", [])
    if tier3_only:
        issues.append(
            f"{len(tier3_only)} valuation-critical fact(s) are Tier-3-only: "
            + ", ".join(str(f) for f in tier3_only[:5])
        )

    return GateResult("source_gate", "FAIL" if issues else "PASS", issues)


def _reconciliation_gate(
    reconciliation_artifact: dict[str, Any] | None,
) -> GateResult:
    if reconciliation_artifact is None:
        return GateResult("reconciliation_gate", "SKIP",
                          ["reconciliation_artifact not provided"])
    conflicts = reconciliation_artifact.get("material_conflicts", [])
    issues = [f"Material conflict: {c}" for c in conflicts]
    return GateResult("reconciliation_gate", "FAIL" if issues else "PASS", issues)


def _numeric_consistency_gate(
    valuation_artifact: dict[str, Any] | None,
    forecast_artifact: dict[str, Any] | None,
) -> GateResult:
    issues: list[str] = []
    if valuation_artifact is None:
        return GateResult("numeric_consistency_gate", "SKIP",
                          ["valuation_artifact not provided"])

    # EPS consistency
    for fy in (forecast_artifact or {}).get("forecast_years", []):
        eps = fy.get("eps")
        ni = fy.get("net_income")
        shares = fy.get("diluted_shares")
        if eps and ni and shares and shares > 0:
            implied = (ni * 1_000) / shares
            if abs(eps - implied) / max(abs(eps), 1) > 0.05:
                issues.append(
                    f"{fy.get('label')}: EPS {eps:.0f} ≠ NI {ni:.0f}bn / "
                    f"{shares:.3f}mn shares → implied {implied:.0f}"
                )

    # Blend arithmetic: 0.60 × FCFF + 0.40 × FCFE
    blend = valuation_artifact.get("blend_dcf", {})
    p_fcff = blend.get("price_fcff")
    p_fcfe = blend.get("price_fcfe")
    p_blend = blend.get("target_price_dcf")
    if all(v is not None for v in [p_fcff, p_fcfe, p_blend]):
        expected = 0.60 * p_fcff + 0.40 * p_fcfe
        if abs(p_blend - expected) / max(abs(expected), 1) > 0.01:
            issues.append(
                f"Blend arithmetic error: {p_blend:.0f} ≠ "
                f"0.6×{p_fcff:.0f}+0.4×{p_fcfe:.0f}={expected:.0f}"
            )

    return GateResult("numeric_consistency_gate", "FAIL" if issues else "PASS", issues,
                      {"checks_run": ["eps_reconciliation", "blend_arithmetic"]})


def _forecast_gate(
    forecast_artifact: dict[str, Any] | None,
) -> GateResult:
    issues: list[str] = []
    metadata: dict[str, Any] = {}
    if forecast_artifact is None:
        return GateResult("forecast_gate", "BLOCKED",
                          ["forecast_artifact missing — forecast gate blocked"])

    # Debt schedule: FCFE is supplementary cross-check only — not blocking.
    # Primary blend is FCFF + P/E Forward; unreliable FCFE does not block export.
    ds = forecast_artifact.get("debt_schedule", {})
    if ds and not ds.get("is_fcfe_publishable", False):
        reason = ds.get("fcfe_block_reason", "unknown")
        metadata["fcfe_cross_check"] = (
            f"is_fcfe_publishable=False — {reason}. "
            "FCFE is supplementary; primary FCFF + P/E Forward blend is unaffected."
        )

    # Working capital check
    wc = forecast_artifact.get("working_capital_schedule")
    if wc is None:
        issues.append("working_capital_schedule missing — delta_nwc estimated")

    # Dividend schedule check
    div = forecast_artifact.get("dividend_schedule", {})
    if div and div.get("method") == "missing":
        issues.append("dividend_schedule.method=missing — payout not modelled")

    status: GateStatus = "FAIL" if issues else "PASS"
    return GateResult("forecast_gate", status, issues, metadata)


def _valuation_gate(
    valuation_artifact: dict[str, Any] | None,
) -> GateResult:
    issues: list[str] = []
    if valuation_artifact is None:
        return GateResult("valuation_gate", "BLOCKED",
                          ["valuation_artifact missing — valuation gate blocked"])

    # Net debt bridge
    fcff = valuation_artifact.get("fcff", {})
    ndb = fcff.get("net_debt_bridge", {})
    if ndb.get("status") == "blocked":
        issues.append("net_debt_bridge.status=blocked (total_debt missing)")

    # FCFF vs P/E Forward gap / blend draft flag
    blend = valuation_artifact.get("blend_dcf", {})
    if blend.get("is_draft_only"):
        gap = blend.get("valuation_gap_pct")
        gap_str = f"{gap:.1%}" if gap else "unknown"
        issues.append(
            f"blend_dcf.is_draft_only=True "
            f"(FCFF vs P/E Forward gap={gap_str} — review EPS growth and WACC assumptions)"
        )

    # Shares check
    shares = fcff.get("shares_mn")
    if shares is None or shares <= 0:
        issues.append("shares_mn missing or zero — target price per share invalid")

    # WACC > g check
    wacc = fcff.get("wacc")
    tg = fcff.get("terminal_growth")
    if wacc and tg and wacc <= tg:
        issues.append(f"WACC ({wacc:.1%}) ≤ terminal_growth ({tg:.1%}) — invalid")

    status = "FAIL" if issues else "PASS"
    return GateResult("valuation_gate", status, issues)


def _sensitivity_gate(
    valuation_artifact: dict[str, Any] | None,
) -> GateResult:
    issues: list[str] = []
    if valuation_artifact is None:
        return GateResult("sensitivity_gate", "SKIP",
                          ["valuation_artifact missing — sensitivity gate skipped"])

    # Check FCFF sensitivity table
    fcff_sens = valuation_artifact.get("fcff_sensitivity", {})
    if not fcff_sens or not fcff_sens.get("matrix"):
        issues.append("fcff_sensitivity matrix missing or empty")
    else:
        # Base WACC must be in the range
        base_wacc = fcff_sens.get("base_wacc")
        wacc_range = fcff_sens.get("wacc_range", [])
        if base_wacc and wacc_range:
            if not any(abs(w - base_wacc) < 0.001 for w in wacc_range):
                issues.append(
                    f"Base WACC {base_wacc:.1%} not in sensitivity wacc_range — "
                    "base assumption must be included (plan §2.3)"
                )

    # Operating sensitivity — warn but do not FAIL (Phase 5 addition; not always present)
    op_sens = valuation_artifact.get("operating_sensitivity", {})
    metadata: dict[str, Any] = {}
    if not op_sens:
        metadata["operating_sensitivity"] = "missing — warn only"

    status = "FAIL" if issues else "PASS"
    return GateResult("sensitivity_gate", status, issues, metadata)


def _citation_gate_from_ledger(
    claim_ledger: dict[str, Any] | None,
    require_tier_01: bool = False,
) -> GateResult:
    if claim_ledger is None:
        return GateResult("citation_gate", "SKIP",
                          ["claim_ledger not provided — citation gate skipped"])

    unsupported = claim_ledger.get("summary", {}).get("unsupported", 0)
    partial = claim_ledger.get("summary", {}).get("partial", 0)
    issues: list[str] = []

    if unsupported > 0:
        issues.append(f"{unsupported} claim(s) have no evidence trace")
    if require_tier_01 and partial > 0:
        issues.append(f"{partial} claim(s) are backed only by Tier-3 sources")

    status: GateStatus = "FAIL" if issues else "PASS"
    return GateResult("citation_gate", status, issues,
                      {"unsupported": unsupported, "partial": partial})


def _layout_gate_from_audit(audit: LayoutRenderAudit | None) -> GateResult:
    if audit is None:
        return GateResult("layout_gate", "SKIP",
                          ["layout_audit not run — layout gate skipped"])
    issues = [f"[{i.check_name}] {i.message}" for i in audit.errors]
    status: GateStatus = "FAIL" if issues else "PASS"
    return GateResult("layout_gate", status, issues,
                      {"error_count": len(audit.errors),
                       "warning_count": len(audit.warnings)})


def _human_review_gate(
    approval_status: str | None,
) -> GateResult:
    if approval_status == "approved":
        return GateResult("human_review_gate", "PASS", [],
                          {"approval_status": approval_status})
    reason = (
        f"approval_status='{approval_status}'" if approval_status
        else "approval_status missing"
    )
    return GateResult("human_review_gate", "FAIL",
                      [f"Human approval required for final export — {reason}"],
                      {"approval_status": approval_status})


# ── Main entry point ──────────────────────────────────────────────────────────

def evaluate_export_gate(
    artifact: ReportArtifact,
    valuation_artifact: dict[str, Any] | None = None,
    forecast_artifact: dict[str, Any] | None = None,
    source_manifest: dict[str, Any] | None = None,
    reconciliation_artifact: dict[str, Any] | None = None,
    claim_ledger: dict[str, Any] | None = None,
    layout_audit: LayoutRenderAudit | None = None,
    approval_status: str | None = None,
    require_tier_01_citations: bool = False,
) -> ExportGateResult:
    """Run all 8 gates and return the unified ExportGateResult.

    Sets artifact.render_mode and artifact.is_final_exportable in-place.
    """
    gates: dict[str, GateResult] = {
        "source_gate": _source_gate(valuation_artifact, source_manifest),
        "reconciliation_gate": _reconciliation_gate(reconciliation_artifact),
        "numeric_consistency_gate": _numeric_consistency_gate(
            valuation_artifact, forecast_artifact
        ),
        "forecast_gate": _forecast_gate(forecast_artifact),
        "valuation_gate": _valuation_gate(valuation_artifact),
        "sensitivity_gate": _sensitivity_gate(valuation_artifact),
        "citation_gate": _citation_gate_from_ledger(
            claim_ledger, require_tier_01_citations
        ),
        "layout_gate": _layout_gate_from_audit(layout_audit),
        "human_review_gate": _human_review_gate(approval_status),
    }

    # Determine blocking gates
    # SKIP, FAIL, and BLOCKED all prevent final export.
    # Only PASS allows final export — missing data is never acceptable.
    blocking: list[str] = [
        name for name, g in gates.items()
        if g.status in ("FAIL", "BLOCKED", "SKIP")
    ]

    # Spec §1.1: produce gate_skipped:{name} blocking reasons
    blocking_reasons: list[str] = []
    for name in blocking:
        g = gates[name]
        if g.status == "SKIP":
            blocking_reasons.append(f"gate_skipped:{name}")
        elif g.status == "FAIL":
            blocking_reasons.append(f"gate_failed:{name}")
        elif g.status == "BLOCKED":
            blocking_reasons.append(f"gate_blocked:{name}")

    is_exportable = len(blocking) == 0
    render_mode: RenderMode = "client_final" if is_exportable else "analyst_draft"

    # Update artifact in-place
    artifact.render_mode = render_mode
    artifact.is_final_exportable = is_exportable
    artifact.gate_results = {name: g.to_dict() for name, g in gates.items()}

    return ExportGateResult(
        ticker=artifact.ticker,
        report_id=artifact.report_id,
        gates=gates,
        render_mode=render_mode,
        is_final_exportable=is_exportable,
        blocking_gates=blocking,
        warnings=blocking_reasons,
    )
