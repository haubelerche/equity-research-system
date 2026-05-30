"""Final source-provenance evaluation gates — Source-Provenance Rebuild, Phase 7.

Seven deterministic gates that block a report when source provenance is weak:

  Gate 1 — Citation Coverage          (every quant/catalyst claim has a citation)
  Gate 2 — Source Tier Validity       (no Tier 4/unknown; final blocks Tier 3-only)
  Gate 3 — Official Source Requirement (final quant claim requires official_document_id)
  Gate 4 — Numeric Consistency        (report values match cited facts within tolerance)
  Gate 5 — Reconciliation Status      (cited facts are matched_official / manual_reviewed)
  Gate 6 — Catalyst Evidence Validity (events have source_document_id + evidence + type)
  Gate 7 — Final Export Approval      (all of 1–6 pass; no blocking issue remains)

All gates are pure functions over plain inputs so they unit-test without a DB.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from backend.catalysts.event_extractor import validate_event
from backend.citations.citation_map import CitationMap
from backend.citations.source_tier_policy import evaluate_source_tier_gate


@dataclass
class GateResult:
    number: int
    name: str
    status: str            # "pass" | "warn" | "fail"
    issues: list[str] = field(default_factory=list)
    checked: int = 0
    details: dict = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status == "pass"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["pass"] = self.passed
        d["issues"] = self.issues[:25]
        return d


def _quant_records(cmap: CitationMap) -> list:
    return [r for r in cmap.values() if not r.is_derived]


# ── Gate 1 — Citation Coverage ─────────────────────────────────────────────────

def gate_citation_coverage(claims: list[dict], cmap: CitationMap) -> GateResult:
    issues: list[str] = []
    checked = 0
    for claim in claims:
        ctype = claim.get("claim_type", "quantitative")
        if ctype not in ("quantitative", "valuation", "catalyst"):
            continue
        checked += 1
        ticker = claim.get("ticker", "")
        period = claim.get("period") or (f"{claim.get('year')}FY" if claim.get("year") else "")
        metric = claim.get("metric", "")
        key = claim.get("citation_key") or f"{ticker}/{period}/{metric}"
        if key not in cmap:
            issues.append(f"claim {key!r} has no citation record")
    status = "pass" if not issues else "fail"
    return GateResult(1, "citation_coverage", status, issues, checked,
                      {"coverage": (checked - len(issues)) / checked if checked else 1.0})


# ── Gate 2 — Source Tier Validity ──────────────────────────────────────────────

def gate_source_tier_validity(cmap: CitationMap, mode: str) -> GateResult:
    res = evaluate_source_tier_gate(cmap, mode=mode)
    status = "pass" if res.export_decision == "PASS" else (
        "warn" if res.export_decision == "PASS_WITH_WARNINGS" else "fail")
    return GateResult(2, "source_tier_validity", status,
                      res.blocking_reasons or res.warnings, res.checked,
                      {"export_decision": res.export_decision, "tier_counts": res.tier_counts})


# ── Gate 3 — Official Source Requirement ───────────────────────────────────────

def gate_official_source_requirement(cmap: CitationMap, mode: str) -> GateResult:
    issues: list[str] = []
    quant = _quant_records(cmap)
    if mode != "final":
        return GateResult(3, "official_source_requirement", "pass", [], len(quant),
                          {"mode": mode, "note": "only enforced in final mode"})
    for r in quant:
        if r.official_document_id is None:
            issues.append(f"{r.key}: final quantitative claim has no official_document_id")
    status = "pass" if not issues else "fail"
    return GateResult(3, "official_source_requirement", status, issues, len(quant))


# ── Gate 4 — Numeric Consistency ───────────────────────────────────────────────

def gate_numeric_consistency(
    report_claims: list[dict], cmap: CitationMap, tolerance_pct: float = 1.0
) -> GateResult:
    issues: list[str] = []
    checked = 0
    for claim in report_claims:
        if claim.get("claim_type") not in ("quantitative", "valuation"):
            continue
        ticker = claim.get("ticker", "")
        period = claim.get("period") or (f"{claim.get('year')}FY" if claim.get("year") else "")
        metric = claim.get("metric", "")
        value = claim.get("value_mentioned", claim.get("value"))
        if value is None or not metric or not period:
            continue
        key = f"{ticker}/{period}/{metric}"
        rec = cmap.get(key)
        if rec is None:
            issues.append(f"{key}: no citation to verify value {value}")
            checked += 1
            continue
        checked += 1
        if rec.value == 0:
            continue
        dev = abs(float(value) - rec.value) / abs(rec.value) * 100
        if dev > tolerance_pct:
            issues.append(f"{key}: report={value} vs fact={rec.value} ({dev:.1f}% > {tolerance_pct}%)")
    status = "pass" if not issues else "fail"
    return GateResult(4, "numeric_consistency", status, issues, checked,
                      {"tolerance_pct": tolerance_pct})


# ── Gate 5 — Reconciliation Status ─────────────────────────────────────────────

_OK_RECON = frozenset({"matched_official", "manual_reviewed"})


def gate_reconciliation_status(cmap: CitationMap, mode: str) -> GateResult:
    issues: list[str] = []
    quant = _quant_records(cmap)
    if mode != "final":
        return GateResult(5, "reconciliation_status", "pass", [], len(quant),
                          {"mode": mode, "note": "only enforced in final mode"})
    for r in quant:
        if r.reconciliation_status not in _OK_RECON:
            issues.append(f"{r.key}: reconciliation_status={r.reconciliation_status!r} (need matched_official/manual_reviewed)")
    status = "pass" if not issues else "fail"
    return GateResult(5, "reconciliation_status", status, issues, len(quant))


# ── Gate 6 — Catalyst Evidence Validity ────────────────────────────────────────

def gate_catalyst_evidence(catalyst_events: list) -> GateResult:
    issues: list[str] = []
    checked = 0
    for ev in catalyst_events:
        checked += 1
        outcome = validate_event(ev)
        if not outcome.valid:
            title = ev.get("event_title") if isinstance(ev, dict) else getattr(ev, "event_title", "?")
            issues.append(f"catalyst {title!r}: {'; '.join(outcome.reasons)}")
    status = "pass" if not issues else "fail"
    return GateResult(6, "catalyst_evidence", status, issues, checked)


# ── Gate 7 — Final Export Approval ─────────────────────────────────────────────

def run_all_gates(
    *,
    claims: list[dict],
    cmap: CitationMap,
    report_claims: list[dict] | None = None,
    catalyst_events: list | None = None,
    mode: str = "final",
    tolerance_pct: float = 1.0,
) -> dict:
    """Run gates 1–6, then gate 7 (final approval). Returns a machine-readable summary."""
    report_claims = report_claims if report_claims is not None else claims
    catalyst_events = catalyst_events or []

    gates = [
        gate_citation_coverage(claims, cmap),
        gate_source_tier_validity(cmap, mode),
        gate_official_source_requirement(cmap, mode),
        gate_numeric_consistency(report_claims, cmap, tolerance_pct),
        gate_reconciliation_status(cmap, mode),
        gate_catalyst_evidence(catalyst_events),
    ]
    blocking = [g for g in gates if g.status == "fail"]
    # Gate 7: final approval requires all gates 1–6 pass (no fails).
    if mode == "final":
        g7_status = "pass" if not blocking else "fail"
        g7_issues = [f"Gate {g.number} ({g.name}) failed" for g in blocking]
    else:
        # Draft can have warnings but cannot be FINAL-approved.
        g7_status = "warn"
        g7_issues = ["draft mode — report cannot be marked final-approved"]
    g7 = GateResult(7, "final_export_approval", g7_status, g7_issues,
                    details={"mode": mode, "failed_gates": [g.number for g in blocking]})
    gates.append(g7)

    final_approved = (mode == "final" and g7.status == "pass")
    return {
        "mode": mode,
        "final_approved": final_approved,
        "export_blocked": (mode == "final" and not final_approved),
        "gates": {g.name: g.to_dict() for g in gates},
        "summary": {g.name: g.status for g in gates},
    }
