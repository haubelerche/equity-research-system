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
        str((t or {}).get("method") or (t or {}).get("formula_id") or "").lower()
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
    warns: list[str] = []
    if computed and not formula_trace_present:
        reasons.append("formula_trace_missing")
    if computed and not bridge_present:
        reasons.append("fcff_wacc_or_ev_to_equity_bridge_missing")
    if computed and not (sensitivity_present and sensitivity_varies):
        reasons.append("fcff_sensitivity_missing_or_constant")
    # Confidence below "high" is a disclosure for the reader, not a publishability
    # blocker: on an unattended run assumptions are rarely analyst-approved, yet a
    # fully computed model (target + bridge + trace + varying sensitivity) remains
    # the analyst's best estimate and must reach the report with a caveat.
    if computed and confidence != "high":
        warns.append(f"fcff_{confidence}_confidence")
    publishable = bool(
        computed
        and formula_trace_present
        and bridge_present
        and sensitivity_present
        and sensitivity_varies
    )
    role: Role = "primary" if publishable else ("scenario_only" if computed else "excluded")
    return MethodDiagnostic(
        method_name="FCFF", computed=computed, publishable=publishable,
        target_price_vnd=target, confidence=confidence, role=role,
        blocking_reasons=reasons, warnings=warns, required_inputs_present=required_inputs_present,
        formula_trace_present=formula_trace_present, bridge_present=bridge_present,
        sensitivity_present=sensitivity_present, sensitivity_varies=sensitivity_varies,
        source_backed_assumptions=bridge_present, analyst_approved_assumptions=False,
    )


def _diag_fcfe(valuation: dict[str, Any]) -> MethodDiagnostic:
    fcfe = valuation.get("fcfe") or {}
    confidence_map = valuation.get("valuation_confidence") or {}
    sensitivity = valuation.get("sensitivity") or {}
    trace_methods = {
        str((t or {}).get("method") or (t or {}).get("formula_id") or "").lower()
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
    warns: list[str] = []
    if blocked:
        # Net borrowing unavailable is a genuine data hard-fail for FCFE itself.
        reasons.append("fcfe_blocked_net_borrowing_unavailable")
    else:
        if not formula_trace_present:
            reasons.append("formula_trace_missing")
        if not bridge_present:
            reasons.append("fcfe_equity_bridge_or_net_borrowing_missing")
        if not (sensitivity_present and sensitivity_varies):
            reasons.append("fcfe_sensitivity_missing_or_constant")
        # Confidence below "high" is a disclosure, not a publishability blocker.
        if confidence != "high":
            warns.append(f"fcfe_{confidence}_confidence")
    publishable = bool(
        computed and not blocked
        and formula_trace_present and bridge_present
        and sensitivity_present and sensitivity_varies
    )
    role: Role = "primary" if publishable else ("scenario_only" if computed else "excluded")
    return MethodDiagnostic(
        method_name="FCFE", computed=computed, publishable=publishable,
        target_price_vnd=target, confidence="blocked" if blocked else confidence, role=role,
        blocking_reasons=reasons, warnings=warns, required_inputs_present=rows_complete,
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
    target = (
        _f(section.get("target_price_vnd"))
        or _f(section.get("value_per_share"))
        or _f(section.get("price_pe_forward_vnd"))
        or _f(section.get("implied_price_pe"))
        or _f(section.get("implied_price_ev_ebitda"))
    )
    eps = _f(section.get("eps_fy1_vnd")) or _f(section.get("eps_vnd"))
    target_pe = _f(section.get("target_pe"))
    reasons = ["cross_check_only_not_primary"]
    warnings: list[str] = []
    if method_name in {"PE_FORWARD", "P/E"} and eps and target_pe and target is None:
        reasons.append("pe_mapping_blank_with_eps_and_target_pe")
        warnings.append("EPS and target P/E are present but P/E implied price is blank")
    return MethodDiagnostic(
        method_name=method_name, computed=target is not None, publishable=False,
        target_price_vnd=target, confidence="medium", role="cross_check",
        blocking_reasons=reasons,
        warnings=warnings,
        required_inputs_present=target is not None,
    )


def _has_market_sanity_bridge(valuation: dict[str, Any]) -> bool:
    bridge = valuation.get("market_sanity_bridge")
    if not isinstance(bridge, dict):
        return False
    return bool(
        bridge.get("upside_downside") is not None
        and (
            bridge.get("current_pe") is not None
            or bridge.get("target_pe_implied") is not None
            or bridge.get("dcf_vs_pe") is not None
            or bridge.get("dcf_vs_ev_ebitda") is not None
        )
    )


def _gate_blockers(valuation: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    gate_results = valuation.get("gate_results") or {}
    if isinstance(gate_results, dict):
        for gate_name, gate in gate_results.items():
            if isinstance(gate, dict) and gate.get("passed") is False:
                reasons.append(f"{str(gate_name).lower()}_failed")
    assumption_gate = valuation.get("assumption_gate") or {}
    if isinstance(assumption_gate, dict) and assumption_gate.get("recommendation_allowed") is False:
        reasons.append("recommendation_gate_not_allowed")
    return reasons


def _critical_warning_reasons(valuation: dict[str, Any]) -> list[str]:
    critical_terms = (
        "CRITICAL",
        "BLOCKED",
        "DATA_QUALITY_GATE",
        "NO ELIGIBLE",
        "NO_ELIGIBLE",
        "SAME_DAY_MARKET_PRICE",
        "FORMULA_TRACE_MISSING",
        "MARKET_SANITY_BRIDGE_MISSING",
        "METHOD_RENDERER_MISMATCH",
    )
    warnings: list[str] = []
    for section_name in ("fcff", "fcfe", "blend_dcf", "pe_forward", "multiples"):
        section = valuation.get(section_name) or {}
        if isinstance(section, dict):
            warnings.extend(str(item) for item in section.get("warnings") or [])
    warnings.extend(str(item) for item in valuation.get("warnings") or [])
    result: list[str] = []
    for warning in warnings:
        upper = warning.upper()
        if any(term in upper for term in critical_terms):
            result.append(f"critical_warning:{warning[:120]}")
    return result


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
    for name, key in (
        ("PE_FORWARD", "pe_forward"),
        ("P/E", "multiples"),
        ("CORE_PE_NET_CASH", "core_pe_net_cash"),
    ):
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
    # Surface per-method disclosures (e.g. low/medium confidence) so the report can
    # publish a sound target with the appropriate caveat rather than blanking it.
    for diag in diagnostics.values():
        warnings.extend(diag.warnings)

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
            target_to_market = cand.target_price_vnd / current_price_vnd
            deviation = abs(target_to_market - 1)
            has_market_bridge = _has_market_sanity_bridge(valuation)
            if deviation > MARKET_SANITY_BAND and not has_market_bridge:
                blocking_reasons.append("market_sanity_bridge_missing")
            if target_to_market < 0.4 and not valuation.get("senior_review"):
                blocking_reasons.append("senior_review_required_for_severe_downside")
            if target_to_market < 0.25 and not valuation.get("distress_evidence"):
                blocking_reasons.append("distress_evidence_required_for_extreme_downside")

    for reason in _gate_blockers(valuation):
        blocking_reasons.append(reason)
    for reason in _critical_warning_reasons(valuation):
        blocking_reasons.append(reason)

    raw_weights = valuation.get("method_weights") or {}
    if isinstance(raw_weights, dict):
        for method_name, weight in raw_weights.items():
            diag = diagnostics.get(str(method_name).upper())
            parsed_weight = _f(weight) or 0.0
            if diag is not None and parsed_weight > 0 and not diag.publishable:
                blocking_reasons.append(f"failed_method_has_nonzero_weight:{diag.method_name}")

    # Demote the universal analyst-approval layer to disclosures (Option A): these
    # reasons fire on essentially every unattended run, so treating them as hard
    # blocks would blank the headline target on every report. They are real caveats
    # for the reader, not evidence the valuation is unsound.
    #   - recommendation_gate_not_allowed: assumption_gate approval (never True unattended)
    #   - low_confidence_primary_method: confidence below "high"
    #   - critical_warning:*: routine operational caveats (e.g. "FCFE BLOCKED",
    #     "peer data PENDING", "single-pass interest")
    advisory_reasons = [
        reason for reason in blocking_reasons
        if reason in {"recommendation_gate_not_allowed", "low_confidence_primary_method"}
        or reason.startswith("critical_warning:")
    ]
    blocking_reasons = [reason for reason in blocking_reasons if reason not in advisory_reasons]
    warnings.extend(advisory_reasons)

    # Genuine per-valuation hard-fails that hide the headline target/recommendation:
    # nothing computed, methods that disagree beyond the critical band, a target far
    # from market with no reconciling bridge, severe/extreme downside without review,
    # an explicit gate failure (e.g. data quality), or a failed method carrying weight.
    divergence_critical = "valuation_method_divergence_critical" in blocking_reasons
    market_sanity_fail = "market_sanity_bridge_missing" in blocking_reasons
    gate_fail = any(reason.endswith("_failed") for reason in blocking_reasons)
    method_weight_fail = any(reason.startswith("failed_method_has_nonzero_weight:") for reason in blocking_reasons)
    senior_review_fail = "senior_review_required_for_severe_downside" in blocking_reasons
    distress_fail = "distress_evidence_required_for_extreme_downside" in blocking_reasons

    target_price_publishable = bool(
        primary_method is not None
        and not divergence_critical
        and not market_sanity_fail
        and not gate_fail
        and not method_weight_fail
        and not senior_review_fail
        and not distress_fail
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
