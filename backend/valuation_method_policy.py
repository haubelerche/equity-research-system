"""Deterministic valuation-method selection policy."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


def select_valuation_methods(
    *,
    archetype: str = "branded_generic_manufacturer",
    fcff: dict[str, Any] | None = None,
    fcfe: dict[str, Any] | None = None,
    valuation_confidence: dict[str, Any] | None = None,
    dividend_history_available: bool = False,
) -> dict[str, Any]:
    """Select methods and explain exclusions without silently falling back."""
    fcff = fcff or {}
    fcfe = fcfe or {}
    valuation_confidence = valuation_confidence or {}
    fcff_confidence = str(valuation_confidence.get("fcff_dcf") or "").lower()
    fcfe_confidence = str(valuation_confidence.get("fcfe_dcf") or "").lower()
    fcff_has_value = fcff.get("target_price_vnd") is not None or fcff.get("value_per_share") is not None
    fcfe_has_value = fcfe.get("target_price_vnd") is not None or fcfe.get("value_per_share") is not None
    fcff_ready = fcff_has_value and fcff_confidence not in {"low", "unavailable"}
    fcfe_ready = fcfe_has_value and fcfe_confidence not in {"low", "unavailable"}
    selected: list[str] = []
    excluded: list[dict[str, str]] = []
    weights: dict[str, float] = {}
    if fcff_ready:
        selected.append("FCFF")
    elif fcff_has_value and fcff_confidence in {"low", "unavailable"}:
        excluded.append({"method": "FCFF", "reason": f"fcff_{fcff_confidence}_confidence"})
    else:
        excluded.append({"method": "FCFF", "reason": "fcff_model_incomplete"})
    if fcfe_ready:
        selected.append("FCFE")
    elif fcfe_has_value and fcfe_confidence in {"low", "unavailable"}:
        excluded.append({"method": "FCFE", "reason": f"fcfe_{fcfe_confidence}_confidence"})
    else:
        excluded.append({"method": "FCFE", "reason": "fcfe_model_incomplete"})
    excluded.append({
        "method": "DDM",
        "reason": "supplementary_only" if dividend_history_available else "dividend_history_insufficient",
    })
    excluded.append({"method": "P/E", "reason": "cross_check_only"})

    if selected == ["FCFF", "FCFE"]:
        weights = {"FCFF": 60.0, "FCFE": 40.0}
    elif selected:
        weights = {selected[0]: 100.0}
    return {
        "schema_version": "1.0",
        "archetype": archetype,
        "selected_methods": selected,
        "method_weights": weights,
        "excluded_methods": excluded,
        "status": "approved_policy" if len(selected) == 2 else "draft_only",
    }


# ===========================================================================
# Single source of truth for valuation publishability (P0 governance)
#
# Core invariant enforced here: "a numeric output exists" must NEVER imply
# "this valuation is publishable". A method may be computed and shown in an
# audit/scenario table yet be forbidden from driving the headline target price
# or BUY/HOLD/SELL recommendation. This module is generic across all tickers —
# no ticker-specific overrides, no assumption tuning, no fabricated rows.
# ===========================================================================

Confidence = Literal["high", "medium", "low", "blocked"]
Role = Literal["primary", "cross_check", "scenario_only", "excluded"]
Status = Literal["publishable", "review_required", "blocked", "missing_artifact"]
Severity = Literal["info", "warning", "critical"]

# Rule 7 — method divergence thresholds (max/min - 1 across usable targets).
DIVERGENCE_WARNING = 0.40
DIVERGENCE_CRITICAL = 0.80
# Rule 8 — market sanity band; beyond this a downside/upside bridge is required.
MARKET_SANITY_BAND = 0.40


@dataclass(frozen=True)
class ExcludedMethod:
    method_name: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"method_name": self.method_name, "reason": self.reason}


@dataclass(frozen=True)
class MethodDiagnostic:
    method_name: str
    computed: bool
    publishable: bool
    target_price_vnd: float | None
    confidence: Confidence
    role: Role
    blocking_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    required_inputs_present: bool = False
    formula_trace_present: bool = False
    bridge_present: bool = False
    sensitivity_present: bool = False
    sensitivity_varies: bool = False
    source_backed_assumptions: bool = False
    analyst_approved_assumptions: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "method_name": self.method_name,
            "computed": self.computed,
            "publishable": self.publishable,
            "target_price_vnd": self.target_price_vnd,
            "confidence": self.confidence,
            "role": self.role,
            "blocking_reasons": list(self.blocking_reasons),
            "warnings": list(self.warnings),
            "required_inputs_present": self.required_inputs_present,
            "formula_trace_present": self.formula_trace_present,
            "bridge_present": self.bridge_present,
            "sensitivity_present": self.sensitivity_present,
            "sensitivity_varies": self.sensitivity_varies,
            "source_backed_assumptions": self.source_backed_assumptions,
            "analyst_approved_assumptions": self.analyst_approved_assumptions,
        }


@dataclass(frozen=True)
class ValuationPublishabilityPolicy:
    ticker: str
    run_id: str | None
    valuation_artifact_path: str | None
    computed_methods: list[str]
    publishable_methods: list[str]
    excluded_methods: list[ExcludedMethod]
    primary_method: str | None
    target_price_publishable: bool
    recommendation_publishable: bool
    final_report_publishable: bool
    status: Status
    severity: Severity
    blocking_reasons: list[str]
    warnings: list[str]
    method_diagnostics: dict[str, MethodDiagnostic]
    divergence_pct: float | None = None
    target_price_vnd: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "run_id": self.run_id,
            "valuation_artifact_path": self.valuation_artifact_path,
            "computed_methods": list(self.computed_methods),
            "publishable_methods": list(self.publishable_methods),
            "excluded_methods": [m.to_dict() for m in self.excluded_methods],
            "primary_method": self.primary_method,
            "target_price_publishable": self.target_price_publishable,
            "recommendation_publishable": self.recommendation_publishable,
            "final_report_publishable": self.final_report_publishable,
            "status": self.status,
            "severity": self.severity,
            "blocking_reasons": list(self.blocking_reasons),
            "warnings": list(self.warnings),
            "divergence_pct": self.divergence_pct,
            "target_price_vnd": self.target_price_vnd,
            "method_diagnostics": {
                name: diag.to_dict() for name, diag in self.method_diagnostics.items()
            },
        }


def _f(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _matrix_varies(value: Any) -> bool:
    numbers: set[float] = set()
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
        elif isinstance(current, (int, float)) and not isinstance(current, bool):
            numbers.add(round(float(current), 6))
    return len(numbers) > 1


def _diag_fcff(valuation: dict[str, Any]) -> MethodDiagnostic:
    fcff = valuation.get("fcff") or {}
    confidence_map = valuation.get("valuation_confidence") or {}
    sensitivity = valuation.get("sensitivity") or {}
    trace_methods = {
        str((t or {}).get("method") or "").lower()
        for t in (valuation.get("formula_traces") or [])
    }
    target = _f(fcff.get("target_price_vnd")) or _f(fcff.get("value_per_share"))
    computed = target is not None
    confidence: Confidence = str(confidence_map.get("fcff_dcf") or "low").lower()  # type: ignore[assignment]
    if confidence not in {"high", "medium", "low", "blocked"}:
        confidence = "low"
    formula_trace_present = "fcff" in trace_methods
    bridge_present = bool(
        fcff.get("wacc_breakdown")
        and fcff.get("equity_value") is not None
        and fcff.get("net_debt_bridge")
        and fcff.get("ev_to_equity_bridge")
    )
    grid = sensitivity.get("fcff_wacc_g")
    sensitivity_present = bool(grid)
    sensitivity_varies = _matrix_varies(grid)
    required_inputs_present = computed and fcff.get("wacc") is not None
    reasons: list[str] = []
    if computed and not formula_trace_present:
        reasons.append("formula_trace_missing")
    if computed and not bridge_present:
        reasons.append("fcff_wacc_or_ev_to_equity_bridge_missing")
    if computed and not (sensitivity_present and sensitivity_varies):
        reasons.append("fcff_sensitivity_missing_or_constant")
    if computed and confidence != "high":
        reasons.append(f"fcff_{confidence}_confidence")
    publishable = bool(
        computed
        and confidence == "high"
        and formula_trace_present
        and bridge_present
        and sensitivity_present
        and sensitivity_varies
    )
    role: Role = "primary" if publishable else ("scenario_only" if computed else "excluded")
    return MethodDiagnostic(
        method_name="FCFF", computed=computed, publishable=publishable,
        target_price_vnd=target, confidence=confidence, role=role,
        blocking_reasons=reasons, required_inputs_present=required_inputs_present,
        formula_trace_present=formula_trace_present, bridge_present=bridge_present,
        sensitivity_present=sensitivity_present, sensitivity_varies=sensitivity_varies,
        source_backed_assumptions=bridge_present, analyst_approved_assumptions=False,
    )


def _diag_fcfe(valuation: dict[str, Any]) -> MethodDiagnostic:
    fcfe = valuation.get("fcfe") or {}
    confidence_map = valuation.get("valuation_confidence") or {}
    sensitivity = valuation.get("sensitivity") or {}
    trace_methods = {
        str((t or {}).get("method") or "").lower()
        for t in (valuation.get("formula_traces") or [])
    }
    rows = fcfe.get("fcfe_table") or []
    rows_complete = bool(rows) and all(
        row.get("fcfe") is not None and row.get("net_borrowing") is not None for row in rows
    )
    target = _f(fcfe.get("target_price_vnd"))
    confidence: Confidence = str(confidence_map.get("fcfe_dcf") or "low").lower()  # type: ignore[assignment]
    if confidence not in {"high", "medium", "low", "blocked"}:
        confidence = "low"
    blocked = (target is None) or (confidence == "blocked") or not rows_complete
    computed = target is not None and rows_complete
    formula_trace_present = "fcfe" in trace_methods
    bridge_present = bool(
        fcfe.get("cost_of_equity_breakdown")
        and fcfe.get("equity_value") is not None
        and rows_complete
    )
    grid = sensitivity.get("fcfe_re_g")
    sensitivity_present = bool(grid)
    sensitivity_varies = _matrix_varies(grid)
    reasons: list[str] = []
    if blocked:
        reasons.append("fcfe_blocked_net_borrowing_unavailable")
    else:
        if not formula_trace_present:
            reasons.append("formula_trace_missing")
        if not bridge_present:
            reasons.append("fcfe_equity_bridge_or_net_borrowing_missing")
        if not (sensitivity_present and sensitivity_varies):
            reasons.append("fcfe_sensitivity_missing_or_constant")
        if confidence != "high":
            reasons.append(f"fcfe_{confidence}_confidence")
    publishable = bool(
        computed and not blocked and confidence == "high"
        and formula_trace_present and bridge_present
        and sensitivity_present and sensitivity_varies
    )
    role: Role = "primary" if publishable else ("scenario_only" if computed else "excluded")
    return MethodDiagnostic(
        method_name="FCFE", computed=computed, publishable=publishable,
        target_price_vnd=target, confidence="blocked" if blocked else confidence, role=role,
        blocking_reasons=reasons, required_inputs_present=rows_complete,
        formula_trace_present=formula_trace_present, bridge_present=bridge_present,
        sensitivity_present=sensitivity_present, sensitivity_varies=sensitivity_varies,
        source_backed_assumptions=bridge_present, analyst_approved_assumptions=False,
    )


def _diag_blend(valuation: dict[str, Any], fcfe_diag: MethodDiagnostic) -> MethodDiagnostic:
    blend = valuation.get("blend_dcf") or {}
    sensitivity = valuation.get("sensitivity") or {}
    target = _f(blend.get("target_price_dcf_vnd"))
    computed = target is not None
    price_fcfe = blend.get("price_fcfe_vnd")
    is_draft_only = blend.get("is_draft_only") is True
    grid = sensitivity.get("blend_grid")
    sensitivity_present = bool(grid)
    sensitivity_varies = _matrix_varies(grid)
    reasons: list[str] = []
    fcfe_available = price_fcfe is not None and fcfe_diag.publishable
    if not fcfe_available:
        reasons.append("fcfe_unavailable_for_blend")
    if not (sensitivity_present and sensitivity_varies):
        reasons.append("blend_sensitivity_missing_or_constant")
    if is_draft_only:
        reasons.append("blend_is_draft_only")
    publishable = bool(computed and fcfe_available and sensitivity_present and sensitivity_varies and not is_draft_only)
    role: Role = "primary" if publishable else ("scenario_only" if computed else "excluded")
    return MethodDiagnostic(
        method_name="BLEND", computed=computed, publishable=publishable,
        target_price_vnd=target, confidence="high" if publishable else "low", role=role,
        blocking_reasons=reasons, required_inputs_present=computed,
        formula_trace_present=True, bridge_present=fcfe_available,
        sensitivity_present=sensitivity_present, sensitivity_varies=sensitivity_varies,
        source_backed_assumptions=fcfe_available, analyst_approved_assumptions=False,
    )


def _diag_cross_check(method_name: str, section: dict[str, Any] | None) -> MethodDiagnostic | None:
    if not section:
        return None
    target = _f(section.get("target_price_vnd")) or _f(section.get("value_per_share"))
    return MethodDiagnostic(
        method_name=method_name, computed=target is not None, publishable=False,
        target_price_vnd=target, confidence="medium", role="cross_check",
        blocking_reasons=["cross_check_only_not_primary"],
        required_inputs_present=target is not None,
    )


def build_valuation_publishability_policy(
    valuation: dict[str, Any] | None,
    *,
    ticker: str,
    run_id: str | None = None,
    valuation_artifact_path: str | None = None,
    current_price_vnd: float | None = None,
) -> ValuationPublishabilityPolicy:
    """Build the single source of truth for what a valuation may publish.

    Generic across all tickers. Never borrows another ticker's artifact, never
    fabricates rows, never tunes assumptions. When inputs are missing or
    governance rules fail, it reports blocked/missing honestly.
    """
    ticker = (ticker or "").strip().upper()

    # Rule 1 — missing or invalid artifact: blocked, never borrowed.
    if not valuation or not isinstance(valuation, dict):
        return ValuationPublishabilityPolicy(
            ticker=ticker, run_id=run_id, valuation_artifact_path=valuation_artifact_path,
            computed_methods=[], publishable_methods=[], excluded_methods=[],
            primary_method=None, target_price_publishable=False,
            recommendation_publishable=False, final_report_publishable=False,
            status="missing_artifact", severity="critical",
            blocking_reasons=["valuation_artifact_missing_for_ticker"], warnings=[],
            method_diagnostics={}, divergence_pct=None, target_price_vnd=None,
        )

    if current_price_vnd is None:
        current_price_vnd = _f(valuation.get("current_price_vnd"))

    fcff_d = _diag_fcff(valuation)
    fcfe_d = _diag_fcfe(valuation)
    blend_d = _diag_blend(valuation, fcfe_d)
    diagnostics: dict[str, MethodDiagnostic] = {"FCFF": fcff_d, "FCFE": fcfe_d, "BLEND": blend_d}
    for name, key in (("PE_FORWARD", "pe_forward"), ("CORE_PE_NET_CASH", "core_pe_net_cash")):
        cross = _diag_cross_check(name, valuation.get(key))
        if cross is not None:
            diagnostics[name] = cross

    computed_methods = [n for n, d in diagnostics.items() if d.computed]
    publishable_methods = [n for n, d in diagnostics.items() if d.publishable]
    excluded_methods = [
        ExcludedMethod(d.method_name, d.blocking_reasons[0] if d.blocking_reasons else "excluded")
        for n, d in diagnostics.items() if not d.publishable
    ]

    blocking_reasons: list[str] = []
    warnings: list[str] = []

    # Primary candidate: only DCF-family methods may be primary, in this order.
    primary_method: str | None = next(
        (n for n in ("BLEND", "FCFF", "FCFE") if diagnostics[n].publishable), None
    )

    # Rule 6 — low-confidence DCF cannot become primary.
    if primary_method is None:
        for n in ("FCFF", "FCFE"):
            d = diagnostics[n]
            if d.computed and d.confidence != "high":
                blocking_reasons.append("low_confidence_primary_method")
                break

    # Rule 7 — method divergence across usable computed targets (exclude blocked
    # FCFE; exclude the composite BLEND to avoid double-counting its legs).
    divergence_targets = [
        d.target_price_vnd
        for n, d in diagnostics.items()
        if n != "BLEND" and d.computed and d.target_price_vnd and d.confidence != "blocked"
    ]
    divergence_pct: float | None = None
    if len(divergence_targets) >= 2:
        hi, lo = max(divergence_targets), min(divergence_targets)
        if lo > 0:
            divergence_pct = hi / lo - 1
            if divergence_pct > DIVERGENCE_CRITICAL:
                blocking_reasons.append("valuation_method_divergence_critical")
            elif divergence_pct >= DIVERGENCE_WARNING:
                warnings.append("valuation_method_divergence_warning")

    # Rule 8 — market sanity. Apply to the value the system would otherwise
    # publish (primary, else the leading computed DCF). Beyond the band, a
    # downside/upside bridge is required.
    sanity_candidate = primary_method or next(
        (n for n in ("FCFF", "BLEND", "FCFE") if diagnostics[n].computed), None
    )
    if sanity_candidate and current_price_vnd:
        cand = diagnostics[sanity_candidate]
        if cand.target_price_vnd and current_price_vnd > 0:
            deviation = abs(cand.target_price_vnd / current_price_vnd - 1)
            if deviation > MARKET_SANITY_BAND and not cand.bridge_present:
                blocking_reasons.append("market_sanity_bridge_missing")

    divergence_critical = "valuation_method_divergence_critical" in blocking_reasons
    market_sanity_fail = "market_sanity_bridge_missing" in blocking_reasons

    target_price_publishable = bool(
        primary_method is not None and not divergence_critical and not market_sanity_fail
    )
    recommendation_publishable = target_price_publishable
    final_report_publishable = target_price_publishable and recommendation_publishable

    target_price_vnd = (
        diagnostics[primary_method].target_price_vnd
        if (target_price_publishable and primary_method)
        else None
    )

    blocking_reasons = sorted(set(blocking_reasons))
    warnings = sorted(set(warnings))
    if target_price_publishable:
        status: Status = "review_required" if warnings else "publishable"
        severity: Severity = "warning" if warnings else "info"
    else:
        status = "blocked"
        severity = "critical"

    return ValuationPublishabilityPolicy(
        ticker=ticker, run_id=run_id, valuation_artifact_path=valuation_artifact_path,
        computed_methods=computed_methods, publishable_methods=publishable_methods,
        excluded_methods=excluded_methods, primary_method=primary_method,
        target_price_publishable=target_price_publishable,
        recommendation_publishable=recommendation_publishable,
        final_report_publishable=final_report_publishable,
        status=status, severity=severity, blocking_reasons=blocking_reasons,
        warnings=warnings, method_diagnostics=diagnostics,
        divergence_pct=divergence_pct, target_price_vnd=target_price_vnd,
    )
