"""Deterministic valuation audit framework.

The audit layer is intentionally orthogonal to valuation math: it records what
was computed, verifies publishability gates, classifies failures with stable
codes, and returns a fail-closed recommendation status for renderers/batch jobs.
"""
from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from backend.valuation_method_policy import (
    build_valuation_publishability_policy,
)


AUDIT_SCHEMA_VERSION = "valuation_audit_v1"
VALUATION_POLICY_VERSION = "valuation_publishability_policy_v2"
REPORT_RENDERER_VERSION = "client_report_view_model_v2"

ERROR_TAXONOMY: dict[str, str] = {
    "DATA_UNIT_ERROR": "Sai đơn vị",
    "SIGN_CONVENTION_ERROR": "Sai dấu",
    "PERIOD_ALIGNMENT_ERROR": "Sai kỳ",
    "SHARE_COUNT_ERROR": "Sai số cổ phiếu",
    "WACC_BRIDGE_ERROR": "Sai cầu nối chi phí vốn",
    "FCF_NORMALIZATION_ERROR": "Sai dòng tiền nền",
    "METHOD_ELIGIBILITY_ERROR": "Phương pháp thiếu dữ liệu vẫn được dùng",
    "MULTIPLES_FALLBACK_ERROR": "Relative valuation fallback hoặc mapping lỗi",
    "MARKET_SANITY_ERROR": "Thiếu đối chiếu thị trường",
    "REPORT_RENDER_ERROR": "Renderer mâu thuẫn engine/gate",
    "RECOMMENDATION_GATE_ERROR": "Cảnh báo nghiêm trọng vẫn ra khuyến nghị",
}

OFFICIAL_RECOMMENDATIONS = {
    "BUY", "HOLD", "SELL", "MUA", "GIỮ", "NẮM GIỮ", "BÁN",
}


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _stable_hash(payload: Any) -> str:
    import json

    encoded = json.dumps(payload or {}, sort_keys=True, default=str).encode("utf-8")
    return sha256(encoded).hexdigest()[:16]


def _formula_methods(valuation: dict[str, Any]) -> set[str]:
    methods: set[str] = set()
    for trace in valuation.get("formula_traces") or []:
        if not isinstance(trace, dict):
            continue
        method = str(trace.get("method") or trace.get("formula_id") or "").lower()
        if method:
            methods.add(method)
    return methods


def _method_weights(valuation: dict[str, Any]) -> dict[str, float]:
    raw = valuation.get("method_weights") or {}
    weights: dict[str, float] = {}
    if not isinstance(raw, dict):
        return weights
    for name, value in raw.items():
        parsed = _number(value)
        if parsed is not None:
            weights[str(name).upper()] = parsed
    return weights


def _target_from_section(section: dict[str, Any] | None, *keys: str) -> float | None:
    if not isinstance(section, dict):
        return None
    for key in keys:
        value = _number(section.get(key))
        if value is not None and value > 0:
            return value
    return None


def build_market_sanity_bridge(valuation: dict[str, Any]) -> dict[str, Any]:
    """Return the market sanity bridge required before recommendation release."""
    blend = valuation.get("blend_dcf") or valuation.get("weighted_target_price") or {}
    multiples = valuation.get("multiples") or {}
    pe = valuation.get("pe_forward") or {}
    fcff = valuation.get("fcff") or {}

    market_price = (
        _number(valuation.get("current_price_vnd"))
        or _number(blend.get("current_price_vnd"))
        or _number(valuation.get("current_price"))
    )
    target_price = (
        _number(blend.get("target_price_dcf_vnd"))
        or _number(blend.get("raw"))
        or _number(valuation.get("target_price_vnd"))
    )
    dcf_price = (
        _number(blend.get("target_price_dcf_vnd"))
        or _number(fcff.get("target_price_vnd"))
        or _number(fcff.get("value_per_share"))
    )
    pe_price = (
        _target_from_section(pe, "target_price_vnd", "price_pe_forward_vnd")
        or _target_from_section(multiples, "implied_price_pe")
    )
    ev_ebitda_price = _target_from_section(multiples, "implied_price_ev_ebitda")
    eps_forward = (
        _number(pe.get("eps_fy1_vnd"))
        or _number(multiples.get("eps_vnd"))
        or _number((valuation.get("core_pe_net_cash") or {}).get("eps_forward_vnd"))
    )
    ebitda_forward = None
    for row in (valuation.get("forecast") or {}).get("forecast_years") or []:
        if isinstance(row, dict) and _number(row.get("ebitda")):
            ebitda_forward = _number(row.get("ebitda"))
            break
    current_ev = None
    target_ev = None
    shares_mn = _number(multiples.get("shares_mn")) or _number(fcff.get("shares_mn"))
    net_debt = _number(multiples.get("net_debt_vnd_bn")) or _number(fcff.get("net_debt"))
    if shares_mn and net_debt is not None and market_price:
        current_ev = market_price * shares_mn / 1000.0 + net_debt
    if shares_mn and net_debt is not None and target_price:
        target_ev = target_price * shares_mn / 1000.0 + net_debt

    def ratio(a: float | None, b: float | None) -> float | None:
        return None if a is None or b in (None, 0) else a / b - 1

    target_to_market = None if target_price is None or market_price in (None, 0) else target_price / market_price
    thresholds = {
        "requires_bridge": bool(target_to_market is not None and (target_to_market < 0.6 or target_to_market > 1.4)),
        "requires_senior_review": bool(target_to_market is not None and target_to_market < 0.4),
        "blocks_without_distress_evidence": bool(target_to_market is not None and target_to_market < 0.25),
    }
    return {
        "market_price": market_price,
        "target_price": target_price,
        "target_to_market": target_to_market,
        "upside_downside": ratio(target_price, market_price),
        "dcf_vs_pe": ratio(dcf_price, pe_price),
        "dcf_vs_ev_ebitda": ratio(dcf_price, ev_ebitda_price),
        "current_pe": None if market_price is None or eps_forward in (None, 0) else market_price / eps_forward,
        "target_pe_implied": None if target_price is None or eps_forward in (None, 0) else target_price / eps_forward,
        "current_ev_ebitda": None if current_ev is None or ebitda_forward in (None, 0) else current_ev / ebitda_forward,
        "target_ev_ebitda": None if target_ev is None or ebitda_forward in (None, 0) else target_ev / ebitda_forward,
        "thresholds": thresholds,
        "bridge_present": bool(valuation.get("market_sanity_bridge")),
        "senior_review_present": bool(valuation.get("senior_review")),
        "distress_evidence_present": bool(valuation.get("distress_evidence")),
    }


def _wacc_bridge_errors(valuation: dict[str, Any]) -> list[str]:
    fcff = valuation.get("fcff") or {}
    bridge = fcff.get("wacc_breakdown") or {}
    if not bridge:
        return []
    re = _number(bridge.get("cost_of_equity"))
    rf = _number(bridge.get("risk_free_rate"))
    beta = _number(bridge.get("beta"))
    erp = _number(bridge.get("equity_risk_premium"))
    premiums = sum(
        value or 0.0
        for value in (
            _number(bridge.get("country_risk_premium")),
            _number(bridge.get("size_premium")),
            _number(bridge.get("liquidity_premium")),
            _number(bridge.get("specific_risk_premium")),
        )
    )
    if None in (re, rf, beta, erp):
        return ["wacc_bridge_components_missing"]
    expected = rf + beta * erp + premiums  # type: ignore[operator]
    if abs(float(re) - expected) > 0.0025 and not bridge.get("reconciliation_note"):
        return ["cost_of_equity_not_reconciled_to_capm_bridge"]
    wacc = _number(fcff.get("wacc")) or _number(bridge.get("wacc"))
    g = _number(fcff.get("terminal_growth"))
    if wacc is not None and g is not None and g >= wacc:
        return ["terminal_growth_not_below_wacc"]
    if wacc is not None and g is not None and wacc - g < 0.02:
        return ["wacc_terminal_growth_spread_too_thin"]
    return []


def _data_invariant_errors(
    valuation: dict[str, Any],
    raw_financial_facts: dict[str, Any] | None,
    normalized_financial_facts: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    facts = normalized_financial_facts or raw_financial_facts or {}
    market_price = _number(valuation.get("current_price_vnd"))
    reported_market_cap = (
        _number(valuation.get("market_cap_vnd"))
        or _number(valuation.get("market_cap"))
        or _number((valuation.get("market_snapshot") or {}).get("market_cap"))
    )
    shares_mn = (
        _number((valuation.get("multiples") or {}).get("shares_mn"))
        or _number((valuation.get("fcff") or {}).get("shares_mn"))
        or _number(facts.get("shares_mn"))
    )
    if market_price and shares_mn and reported_market_cap:
        implied = market_price * shares_mn * 1_000_000
        if abs(implied - reported_market_cap) / reported_market_cap > 0.05:
            errors.append({
                "code": "DATA_UNIT_ERROR",
                "severity": "critical",
                "message": "implied_market_cap differs from reported_market_cap by more than 5%",
                "details": {
                    "implied_market_cap": implied,
                    "reported_market_cap": reported_market_cap,
                },
            })
    if shares_mn is not None and shares_mn <= 0:
        errors.append({
            "code": "SHARE_COUNT_ERROR",
            "severity": "critical",
            "message": "shares_outstanding must be positive",
        })
    return errors


def _multiples_mapping_errors(valuation: dict[str, Any]) -> list[dict[str, Any]]:
    pe = valuation.get("pe_forward") or {}
    multiples = valuation.get("multiples") or {}
    eps = _number(pe.get("eps_fy1_vnd")) or _number(multiples.get("eps_vnd"))
    target_pe = _number(pe.get("target_pe")) or _number(multiples.get("target_pe"))
    pe_price = (
        _target_from_section(pe, "target_price_vnd", "price_pe_forward_vnd")
        or _target_from_section(multiples, "implied_price_pe")
    )
    if eps and eps > 0 and target_pe and target_pe > 0 and pe_price is None:
        return [{
            "code": "MULTIPLES_FALLBACK_ERROR",
            "severity": "critical",
            "message": "EPS and target P/E are available but P/E implied price is blank",
            "details": {"eps": eps, "target_pe": target_pe},
        }]
    return []


def _renderer_errors(
    valuation: dict[str, Any],
    policy: Any,
    report_draft: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not report_draft:
        return []
    errors: list[dict[str, Any]] = []
    report_target = _number(report_draft.get("target_price") or report_draft.get("target_price_vnd"))
    report_rec = str(report_draft.get("recommendation") or "").strip().upper()
    if not policy.recommendation_publishable and report_rec in OFFICIAL_RECOMMENDATIONS:
        errors.append({
            "code": "REPORT_RENDER_ERROR",
            "severity": "critical",
            "message": "report displays an official recommendation while policy blocks publication",
            "details": {"recommendation": report_rec},
        })
    if policy.target_price_publishable and report_target and policy.target_price_vnd:
        if abs(report_target - policy.target_price_vnd) > 1:
            errors.append({
                "code": "REPORT_RENDER_ERROR",
                "severity": "critical",
                "message": "report target price differs from valuation policy target",
                "details": {"report_target": report_target, "policy_target": policy.target_price_vnd},
            })
    return errors


def _method_eligibility(valuation: dict[str, Any], policy: Any) -> dict[str, Any]:
    traces = _formula_methods(valuation)
    weights = _method_weights(valuation)
    result: dict[str, Any] = {}
    for name, diag in policy.method_diagnostics.items():
        weight = weights.get(name, 0.0)
        status = "pass" if diag.publishable else ("review" if diag.computed else "fail")
        if status == "fail" and weight:
            status = "fail"
        result[name] = {
            "status": status,
            "computed": diag.computed,
            "target_price_vnd": diag.target_price_vnd,
            "required_inputs_available": diag.required_inputs_present,
            "formula_trace_complete": diag.formula_trace_present or name.lower() in traces,
            "sanity_check_passed": not diag.blocking_reasons,
            "method_confidence": diag.confidence,
            "renderer_consistency_passed": True,
            "weight": weight,
            "blocking_reasons": list(diag.blocking_reasons),
            "warnings": list(diag.warnings),
        }
    return result


def build_valuation_audit(
    valuation: dict[str, Any] | None,
    *,
    ticker: str | None = None,
    run_id: str | None = None,
    raw_financial_facts: dict[str, Any] | None = None,
    normalized_financial_facts: dict[str, Any] | None = None,
    ratio_results: dict[str, Any] | None = None,
    forecast_results: dict[str, Any] | None = None,
    gate_results: dict[str, Any] | None = None,
    report_draft: dict[str, Any] | None = None,
    final_report_path: str | None = None,
    explanation_path: str | None = None,
) -> dict[str, Any]:
    """Build a single per-ticker audit artifact for batch debugging."""
    valuation = valuation or {}
    resolved_ticker = (ticker or valuation.get("ticker") or "").strip().upper()
    resolved_run_id = run_id or valuation.get("run_id") or valuation.get("generated_at") or "unknown_run"
    generated_at = datetime.now(UTC).isoformat()
    market_bridge = build_market_sanity_bridge(valuation)
    policy = build_valuation_publishability_policy(
        valuation,
        ticker=resolved_ticker,
        run_id=str(resolved_run_id),
        current_price_vnd=market_bridge.get("market_price"),
    )
    method_eligibility = _method_eligibility(valuation, policy)

    errors: list[dict[str, Any]] = []
    errors.extend(_data_invariant_errors(valuation, raw_financial_facts, normalized_financial_facts))
    errors.extend(_multiples_mapping_errors(valuation))
    errors.extend(_renderer_errors(valuation, policy, report_draft))

    for reason in _wacc_bridge_errors(valuation):
        errors.append({"code": "WACC_BRIDGE_ERROR", "severity": "critical", "message": reason})

    weights = _method_weights(valuation)
    for method, item in method_eligibility.items():
        if item["status"] == "fail" and item["weight"]:
            errors.append({
                "code": "METHOD_ELIGIBILITY_ERROR",
                "severity": "critical",
                "message": f"{method} failed eligibility but has non-zero weight",
                "details": {"method": method, "weight": item["weight"]},
            })

    if market_bridge["thresholds"]["requires_bridge"] and not market_bridge["bridge_present"]:
        errors.append({
            "code": "MARKET_SANITY_ERROR",
            "severity": "critical",
            "message": "target price is outside market sanity band without market_sanity_bridge",
            "details": market_bridge,
        })
    if market_bridge["thresholds"]["requires_senior_review"] and not market_bridge["senior_review_present"]:
        errors.append({
            "code": "MARKET_SANITY_ERROR",
            "severity": "critical",
            "message": "target price is below 40% of market price without senior_review",
            "details": market_bridge,
        })
    if market_bridge["thresholds"]["blocks_without_distress_evidence"] and not market_bridge["distress_evidence_present"]:
        errors.append({
            "code": "MARKET_SANITY_ERROR",
            "severity": "critical",
            "message": "target price is below 25% of market price without distress evidence",
            "details": market_bridge,
        })

    gate_payload = gate_results or valuation.get("gate_results") or {}
    assumption_gate = valuation.get("assumption_gate") or {}
    if assumption_gate and assumption_gate.get("recommendation_allowed") is False:
        errors.append({
            "code": "RECOMMENDATION_GATE_ERROR",
            "severity": "critical",
            "message": "assumption gate blocks final recommendation",
            "details": {"blocking_reasons": assumption_gate.get("blocking_reasons") or []},
        })
    if not policy.recommendation_publishable:
        errors.append({
            "code": "RECOMMENDATION_GATE_ERROR",
            "severity": "critical",
            "message": "valuation publishability policy blocks final recommendation",
            "details": {"blocking_reasons": policy.blocking_reasons},
        })

    critical_errors = [e for e in errors if e.get("severity") == "critical"]
    any_primary_pass = any(
        method_eligibility.get(name, {}).get("status") == "pass"
        for name in ("BLEND", "FCFF", "FCFE")
    )
    final_recommendation = "Chưa phát hành" if critical_errors or not any_primary_pass else "Đủ điều kiện phát hành"
    target_price_status = (
        "Không đủ điều kiện công bố"
        if critical_errors or not policy.target_price_publishable
        else "Có thể công bố"
    )
    report_status = "Draft-only" if critical_errors or not policy.final_report_publishable else "Publishable"

    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "ticker": resolved_ticker,
        "run_id": str(resolved_run_id),
        "run_timestamp": generated_at,
        "input_snapshot_id": valuation.get("snapshot_id") or valuation.get("input_snapshot_id"),
        "model_config_hash": _stable_hash(valuation.get("assumptions")),
        "formula_engine_version": valuation.get("formula_version") or "unknown",
        "valuation_policy_version": VALUATION_POLICY_VERSION,
        "report_renderer_version": REPORT_RENDERER_VERSION,
        "market_price_timestamp": (
            valuation.get("market_price_as_of")
            or valuation.get("price_as_of_date")
            or valuation.get("snapshot_as_of")
        ),
        "taxonomy": ERROR_TAXONOMY,
        "raw_financial_facts": raw_financial_facts or {},
        "normalized_financial_facts": normalized_financial_facts or {},
        "ratio_results": ratio_results or valuation.get("ratios") or {},
        "forecast_results": forecast_results or valuation.get("forecast") or {},
        "valuation_input_pack": valuation.get("valuation_input_pack") or {},
        "valuation_results": valuation,
        "method_eligibility": method_eligibility,
        "market_sanity_bridge": market_bridge,
        "gate_results": gate_payload,
        "policy": policy.to_dict(),
        "report_draft": report_draft or {},
        "final_report_pdf": final_report_path,
        "explanation_pdf": explanation_path,
        "errors": errors,
        "critical_warning_count": len(critical_errors),
        "eligible_primary_method_count": sum(
            method_eligibility.get(name, {}).get("status") == "pass"
            for name in ("BLEND", "FCFF", "FCFE")
        ),
        "recommendation_status": {
            "recommendation": final_recommendation,
            "target_price_status": target_price_status,
            "report_status": report_status,
            "draft_only": report_status == "Draft-only",
        },
        "summary": {
            "market_price": market_bridge.get("market_price"),
            "target_price": market_bridge.get("target_price"),
            "upside_downside": market_bridge.get("upside_downside"),
            "method_count_passed": sum(item["status"] == "pass" for item in method_eligibility.values()),
            "critical_error_codes": sorted({e["code"] for e in critical_errors}),
            "method_weights": weights,
            "publishable": report_status == "Publishable",
        },
    }
