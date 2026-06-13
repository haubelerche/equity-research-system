"""Unified export gate — Phase 7 master plan §2.4 / hard gates summary.

Aggregates all 8 required gates into a single ExportGateResult:

  source_gate              — material facts have source trace; no Tier-3-only valuation
  reconciliation_gate      — official vs secondary facts do not materially conflict
  numeric_consistency_gate — formulas, shares, units, signs reconcile
  forecast_gate            — debt, dividend, working capital, tax are present and valid
  valuation_gate           — FCFF + FCFE blend (60/40), WACC/Re, terminal growth, net debt, shares valid
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
    p_fcff = blend.get("price_fcff_vnd")
    p_fcfe = blend.get("price_fcfe_vnd")
    p_blend = blend.get("target_price_dcf_vnd")
    if all(v is not None for v in [p_fcff, p_fcfe, p_blend]):
        expected = 0.60 * p_fcff + 0.40 * p_fcfe
        if abs(p_blend - expected) / max(abs(expected), 1) > 0.01:
            issues.append(
                f"Blend arithmetic error: {p_blend:.0f} ≠ "
                f"0.6×{p_fcff:.0f}+0.4×{p_fcfe:.0f}={expected:.0f}"
            )

    # Dividend yield reconciliation: DY = DPS / Current Price
    blend = valuation_artifact.get("blend_dcf", {})
    current_price = blend.get("current_price_vnd")
    if current_price and current_price > 0:
        for fy in (forecast_artifact or {}).get("forecast_years", []):
            dps = fy.get("dps")
            dy = fy.get("dividend_yield")
            if dps is not None and dy is not None:
                expected_dy = dps / current_price
                if abs(dy - expected_dy) > 0.005:
                    issues.append(
                        f"{fy.get('label')}: dividend_yield {dy:.2%} != DPS {dps:.0f} / "
                        f"price {current_price:.0f} -> implied {expected_dy:.2%}"
                    )

    # P/E reconciliation: P/E = Current Price / EPS
    for fy in (forecast_artifact or {}).get("forecast_years", []):
        pe = fy.get("pe")
        eps = fy.get("eps")
        if pe is not None and eps is not None and eps > 0 and current_price and current_price > 0:
            expected_pe = current_price / eps
            if abs(pe - expected_pe) / max(abs(expected_pe), 1) > 0.05:
                issues.append(
                    f"{fy.get('label')}: P/E {pe:.1f} != price {current_price:.0f} / "
                    f"EPS {eps:.0f} -> implied {expected_pe:.1f}"
                )

    checks_run = [
        "eps_reconciliation", "blend_arithmetic",
        "dividend_yield_reconciliation", "pe_reconciliation",
    ]
    return GateResult("numeric_consistency_gate", "FAIL" if issues else "PASS", issues,
                      {"checks_run": checks_run})


def _forecast_gate(
    forecast_artifact: dict[str, Any] | None,
) -> GateResult:
    issues: list[str] = []
    metadata: dict[str, Any] = {}
    if forecast_artifact is None:
        return GateResult("forecast_gate", "BLOCKED",
                          ["forecast_artifact missing — forecast gate blocked"])

    # Debt schedule: FCFE is primary (40% blend weight).
    # Unpublishable FCFE blocks final export — analyst must approve debt path.
    ds = forecast_artifact.get("debt_schedule", {})
    if ds and not ds.get("is_fcfe_publishable", False):
        reason = ds.get("fcfe_block_reason", "unknown")
        issues.append(
            f"debt_schedule.is_fcfe_publishable=False — {reason}. "
            "FCFE carries 40% blend weight; final export blocked until debt schedule is approved."
        )

    # Working capital check
    wc = forecast_artifact.get("working_capital_schedule")
    if wc is None:
        issues.append("working_capital_schedule missing — delta_nwc estimated")

    # Dividend schedule check
    div = forecast_artifact.get("dividend_schedule", {})
    if div and div.get("method") == "missing":
        issues.append("dividend_schedule.method=missing — payout not modelled")

    _check_profit_growth_vs_revenue_growth(forecast_artifact, issues)
    _check_cash_accumulation_without_dividend_policy(forecast_artifact, issues)

    status: GateStatus = "FAIL" if issues else "PASS"
    return GateResult("forecast_gate", status, issues, metadata)


def _check_profit_growth_vs_revenue_growth(
    forecast_artifact: dict[str, Any],
    issues: list[str],
) -> None:
    """Block unexplained profit jumps that exceed revenue growth by >15 ppts."""
    if forecast_artifact.get("margin_bridge") or forecast_artifact.get("profit_growth_explanation"):
        return
    rows = [
        row for row in forecast_artifact.get("forecast_years", [])
        if isinstance(row, dict)
    ]
    for previous, current in zip(rows, rows[1:]):
        rev_growth = current.get("revenue_growth")
        profit_growth = current.get("net_income_growth")
        if rev_growth is None:
            prev_rev = previous.get("revenue")
            curr_rev = current.get("revenue")
            if prev_rev not in (None, 0) and curr_rev is not None:
                rev_growth = curr_rev / prev_rev - 1
        if profit_growth is None:
            prev_profit = previous.get("net_income")
            curr_profit = current.get("net_income")
            if prev_profit not in (None, 0) and curr_profit is not None:
                profit_growth = curr_profit / prev_profit - 1
        if rev_growth is None or profit_growth is None:
            continue
        if profit_growth - rev_growth > 0.15 and not current.get("margin_bridge"):
            label = current.get("label", "forecast period")
            issues.append(
                f"{label}: net income growth {profit_growth:.1%} exceeds revenue growth "
                f"{rev_growth:.1%} by more than 15 percentage points without a margin bridge."
            )


def _cash_by_label(forecast_artifact: dict[str, Any]) -> dict[str, float]:
    cash: dict[str, float] = {}
    for row in forecast_artifact.get("forecast_years", []):
        if isinstance(row, dict) and row.get("label") and row.get("cash") is not None:
            cash[str(row["label"])] = float(row["cash"])
    for row in (forecast_artifact.get("cash_sweep_artifact") or {}).get("year_results", []):
        if not isinstance(row, dict):
            continue
        label = row.get("year_label") or row.get("label")
        value = row.get("computed_ending_cash") if row.get("computed_ending_cash") is not None else row.get("cash")
        if label and value is not None:
            cash[str(label)] = float(value)
    return cash


def _dividend_policy_missing(forecast_artifact: dict[str, Any]) -> bool:
    schedule = forecast_artifact.get("dividend_schedule")
    if not schedule:
        return True
    if schedule.get("method") == "missing":
        return True
    rows = schedule.get("forecast_rows") or []
    if rows and any((row.get("cash_dividend") or 0) > 0 for row in rows if isinstance(row, dict)):
        return False
    return not bool(schedule.get("policy") or schedule.get("payout_ratio"))


def _check_cash_accumulation_without_dividend_policy(
    forecast_artifact: dict[str, Any],
    issues: list[str],
) -> None:
    """Block mature-profitable forecasts that accumulate excess cash with no payout policy."""
    if not _dividend_policy_missing(forecast_artifact):
        return
    cash_by_label = _cash_by_label(forecast_artifact)
    rows = [
        row for row in forecast_artifact.get("forecast_years", [])
        if isinstance(row, dict) and row.get("label")
    ]
    cash_series: list[float] = []
    max_cash_to_revenue = 0.0
    has_profit = False
    for row in rows:
        label = str(row["label"])
        cash = cash_by_label.get(label)
        revenue = row.get("revenue")
        if row.get("net_income") is not None and row.get("net_income") > 0:
            has_profit = True
        if cash is None:
            continue
        cash_series.append(cash)
        if revenue not in (None, 0):
            max_cash_to_revenue = max(max_cash_to_revenue, cash / revenue)
    if len(cash_series) < 2 or not has_profit:
        return
    monotonic_cash = all(curr >= prev for prev, curr in zip(cash_series, cash_series[1:]))
    if monotonic_cash and max_cash_to_revenue > 0.75:
        issues.append(
            "cash accumulation anomaly: projected cash exceeds 75% of revenue and rises "
            "monotonically while dividend policy is missing."
        )


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

    # FCFF/FCFE gap / blend draft flag
    blend = valuation_artifact.get("blend_dcf", {})
    if blend.get("is_draft_only"):
        gap = blend.get("fcff_fcfe_gap_pct")
        gap_str = f"{gap:.1%}" if gap else "unknown"
        issues.append(
            f"blend_dcf.is_draft_only=True "
            f"(FCFF/FCFE gap={gap_str} — audit net borrowing, net debt, CAPEX, NWC)"
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

    # Re > g check (FCFE)
    fcfe = valuation_artifact.get("fcfe", {})
    re = fcfe.get("cost_of_equity")
    tg_fcfe = fcfe.get("terminal_growth")
    if re and tg_fcfe and re <= tg_fcfe:
        issues.append(f"Re ({re:.1%}) ≤ terminal_growth ({tg_fcfe:.1%}) — FCFE invalid")

    # FCFF bridge check
    if fcff and not fcff.get("enterprise_value"):
        issues.append("FCFF enterprise_value missing — FCFF bridge incomplete")

    # FCFE bridge check
    if fcfe and not fcfe.get("equity_value"):
        issues.append("FCFE equity_value missing — FCFE bridge incomplete")

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
        _check_sensitivity_base_cell_matches_target(valuation_artifact, fcff_sens, issues)

    # Operating sensitivity — warn but do not FAIL (Phase 5 addition; not always present)
    op_sens = valuation_artifact.get("operating_sensitivity", {})
    metadata: dict[str, Any] = {}
    if not op_sens:
        metadata["operating_sensitivity"] = "missing — warn only"

    status = "FAIL" if issues else "PASS"
    return GateResult("sensitivity_gate", status, issues, metadata)


def _target_price_from_valuation(valuation_artifact: dict[str, Any]) -> float | None:
    blend = valuation_artifact.get("blend_dcf", {}) or {}
    fcff = valuation_artifact.get("fcff", {}) or {}
    for candidate in (
        blend.get("target_price_dcf_vnd"),
        blend.get("target_price_vnd"),
        fcff.get("target_price_vnd"),
        valuation_artifact.get("target_price_vnd"),
    ):
        if candidate is not None:
            return float(candidate)
    return None


def _matrix_value(matrix: Any, row_index: int, col_index: int, row_key: Any, col_key: Any) -> float | None:
    if isinstance(matrix, list):
        try:
            value = matrix[row_index][col_index]
        except (IndexError, TypeError):
            return None
        return float(value) if value is not None else None
    if not isinstance(matrix, dict):
        return None

    row_candidates = [
        row_key,
        str(row_key),
        f"{float(row_key):.3f}" if isinstance(row_key, (int, float)) else None,
        f"{float(row_key):.4f}".rstrip("0").rstrip(".") if isinstance(row_key, (int, float)) else None,
    ]
    col_candidates = [
        col_key,
        str(col_key),
        f"{float(col_key):.3f}" if isinstance(col_key, (int, float)) else None,
        f"{float(col_key):.4f}".rstrip("0").rstrip(".") if isinstance(col_key, (int, float)) else None,
    ]
    for rk in [c for c in row_candidates if c is not None]:
        row = matrix.get(rk)
        if not isinstance(row, dict):
            continue
        for ck in [c for c in col_candidates if c is not None]:
            value = row.get(ck)
            if value is not None:
                return float(value)
    return None


def _check_sensitivity_base_cell_matches_target(
    valuation_artifact: dict[str, Any],
    fcff_sens: dict[str, Any],
    issues: list[str],
) -> None:
    target = _target_price_from_valuation(valuation_artifact)
    base_wacc = fcff_sens.get("base_wacc")
    base_g = (
        fcff_sens.get("base_terminal_growth")
        if fcff_sens.get("base_terminal_growth") is not None
        else fcff_sens.get("base_g")
    )
    wacc_range = fcff_sens.get("wacc_range") or []
    g_range = fcff_sens.get("g_range") or fcff_sens.get("terminal_growth_range") or []
    matrix = fcff_sens.get("matrix")
    if target is None or base_wacc is None or base_g is None or not wacc_range or not g_range:
        return
    try:
        row_index = min(range(len(wacc_range)), key=lambda i: abs(float(wacc_range[i]) - float(base_wacc)))
        col_index = min(range(len(g_range)), key=lambda i: abs(float(g_range[i]) - float(base_g)))
    except (TypeError, ValueError):
        return
    value = _matrix_value(matrix, row_index, col_index, wacc_range[row_index], g_range[col_index])
    if value is None:
        return
    if abs(value - target) / max(abs(target), 1.0) > 0.01:
        issues.append(
            f"sensitivity base cell {value:,.0f} differs from target price {target:,.0f} by more than 1%."
        )


def _sensitivity_gate_v2(
    valuation_artifact: dict[str, Any] | None,
) -> GateResult:
    issues: list[str] = []
    if valuation_artifact is None:
        return GateResult("sensitivity_gate", "SKIP",
                          ["valuation_artifact missing - sensitivity gate skipped"])

    sensitivity = valuation_artifact.get("sensitivity", {}) or {}
    fcff_sens = valuation_artifact.get("fcff_sensitivity") or sensitivity.get("fcff_wacc_g") or {}
    fcfe_sens = valuation_artifact.get("fcfe_sensitivity") or sensitivity.get("fcfe_re_g") or {}
    blend_sens = valuation_artifact.get("blend_sensitivity") or sensitivity.get("blend_grid") or {}

    if not fcff_sens or not fcff_sens.get("matrix"):
        issues.append("fcff_sensitivity matrix missing or empty")
    else:
        _check_axis_contains_base_v2("FCFF", "WACC", fcff_sens.get("base_wacc"), fcff_sens.get("wacc_range") or [], issues)
        _check_sensitivity_base_cell_v2(
            valuation_artifact,
            fcff_sens,
            issues,
            axis="fcff",
            target=_target_price_from_valuation_v2(valuation_artifact, "fcff"),
        )

    if not fcfe_sens or not fcfe_sens.get("matrix"):
        issues.append("fcfe_sensitivity matrix missing or empty")
    else:
        _check_axis_contains_base_v2("FCFE", "Re", fcfe_sens.get("base_re"), fcfe_sens.get("re_range") or [], issues)
        _check_sensitivity_base_cell_v2(
            valuation_artifact,
            fcfe_sens,
            issues,
            axis="fcfe",
            target=_target_price_from_valuation_v2(valuation_artifact, "fcfe"),
        )

    if not blend_sens or not blend_sens.get("matrix"):
        issues.append("blend_sensitivity matrix missing or empty")
    else:
        _check_sensitivity_base_cell_v2(
            valuation_artifact,
            blend_sens,
            issues,
            axis="blend",
            target=_target_price_from_valuation_v2(valuation_artifact, "blend"),
        )

    op_sens = valuation_artifact.get("operating_sensitivity", {})
    metadata: dict[str, Any] = {}
    if not op_sens:
        metadata["operating_sensitivity"] = "missing - warn only"

    status = "FAIL" if issues else "PASS"
    return GateResult("sensitivity_gate", status, issues, metadata)


def _target_price_from_valuation_v2(
    valuation_artifact: dict[str, Any],
    target_kind: str,
) -> float | None:
    blend = valuation_artifact.get("blend_dcf", {}) or {}
    fcff = valuation_artifact.get("fcff", {}) or {}
    fcfe = valuation_artifact.get("fcfe", {}) or {}
    if target_kind == "fcff":
        candidates = (
            blend.get("price_fcff_vnd"),
            fcff.get("target_price_vnd"),
            valuation_artifact.get("price_fcff_vnd"),
        )
    elif target_kind == "fcfe":
        candidates = (
            blend.get("price_fcfe_vnd"),
            fcfe.get("target_price_vnd"),
            valuation_artifact.get("price_fcfe_vnd"),
        )
    else:
        candidates = (
            blend.get("target_price_dcf_vnd"),
            blend.get("target_price_vnd"),
            valuation_artifact.get("target_price_vnd"),
        )
    for candidate in candidates:
        if candidate is not None:
            return float(candidate)
    return None


def _check_axis_contains_base_v2(
    label: str,
    axis_label: str,
    base_value: Any,
    axis_range: list[Any],
    issues: list[str],
) -> None:
    if base_value is None or not axis_range:
        return
    try:
        if not any(abs(float(v) - float(base_value)) < 0.001 for v in axis_range):
            issues.append(
                f"{label} base {axis_label} {float(base_value):.1%} not in sensitivity range."
            )
    except (TypeError, ValueError):
        return


def _check_sensitivity_base_cell_v2(
    valuation_artifact: dict[str, Any],
    table: dict[str, Any],
    issues: list[str],
    *,
    axis: str,
    target: float | None,
) -> None:
    row_range, col_range, base_row, base_col = _sensitivity_axes_v2(valuation_artifact, table, axis)
    matrix = table.get("matrix")
    if target is None or base_row is None or base_col is None or not row_range or not col_range:
        return
    try:
        row_index = min(range(len(row_range)), key=lambda i: abs(float(row_range[i]) - float(base_row)))
        col_index = min(range(len(col_range)), key=lambda i: abs(float(col_range[i]) - float(base_col)))
    except (TypeError, ValueError):
        return
    value = _matrix_value(matrix, row_index, col_index, row_range[row_index], col_range[col_index])
    if value is None:
        return
    if abs(value - target) / max(abs(target), 1.0) > 0.01:
        issues.append(
            f"{axis} sensitivity base cell {value:,.0f} differs from target price {target:,.0f} by more than 1%."
        )


def _sensitivity_axes_v2(
    valuation_artifact: dict[str, Any],
    table: dict[str, Any],
    axis: str,
) -> tuple[list[Any], list[Any], float | None, float | None]:
    if axis == "fcff":
        fcff = valuation_artifact.get("fcff", {}) or {}
        base_g = table.get("base_terminal_growth", table.get("base_g"))
        if base_g is None:
            base_g = fcff.get("terminal_growth")
        return (
            table.get("wacc_range") or [],
            table.get("g_range") or table.get("terminal_growth_range") or [],
            table.get("base_wacc") or fcff.get("wacc"),
            base_g,
        )
    if axis == "fcfe":
        fcfe = valuation_artifact.get("fcfe", {}) or {}
        base_g = table.get("base_terminal_growth", table.get("base_g"))
        if base_g is None:
            base_g = fcfe.get("terminal_growth")
        return (
            table.get("re_range") or [],
            table.get("g_range") or table.get("terminal_growth_range") or [],
            table.get("base_re") or fcfe.get("cost_of_equity"),
            base_g,
        )

    blend = valuation_artifact.get("blend_dcf", {}) or {}
    return (
        table.get("price_fcff_range") or [],
        table.get("price_fcfe_range") or [],
        blend.get("price_fcff_vnd"),
        blend.get("price_fcfe_vnd"),
    )


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
        "sensitivity_gate": _sensitivity_gate_v2(valuation_artifact),
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
