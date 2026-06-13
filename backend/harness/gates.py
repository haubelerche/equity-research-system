from __future__ import annotations

import re
from math import isclose
from typing import Any

_FY_PATTERN = re.compile(r"^20\d{2}FY$")
_METRIC_REF_PATTERN = re.compile(r"\b[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+\b")
_PERIOD_REF_PATTERN = re.compile(r"\b20\d{2}(?:FY|A|F)?\b")

_REQUIRED_REPORT_SECTIONS = {
    "cover_investment_summary": ("cover_investment_summary", "investment_summary"),
    "company_overview": ("company_overview",),
    "recent_financial_performance": ("recent_financial_performance",),
    "driver_based_forecast": ("driver_based_forecast",),
    "valuation_and_recommendation": ("valuation_and_recommendation", "valuation"),
    "risks_and_monitoring_factors": ("risks_and_monitoring_factors", "risks"),
    "forecast_financial_summary": ("forecast_financial_summary",),
}
_REQUIRED_TABLES = {
    "trading_snapshot",
    "company_overview",
    "recent_financial_results",
    "business_plan_completion",
    "forecast_assumptions",
    "valuation_summary",
    "dcf_assumptions",
    "fcff_fcfe_bridge",
    "forecast_financial_statement_summary",
    "risk_and_monitoring_factors",
}
_REQUIRED_CHARTS = {
    "stock_price_vs_benchmark",
    "revenue_by_channel",
    "product_group_revenue_or_market_share",
    "gross_margin_net_margin_trend",
    "forecast_revenue",
    "forecast_gross_profit_or_margin",
}
_CRITIC_MINIMUM_SCORES = {
    "thesis_strength": 8.0,
    "driver_logic": 8.0,
    "forecast_consistency": 8.0,
    "valuation_coherence": 8.0,
    "evidence_depth": 7.5,
    "sector_specificity": 8.0,
    "risk_balance": 7.5,
    "table_chart_completeness": 8.0,
    "narrative_quality": 8.0,
    "numeric_integrity": 9.5,
    "citation_integrity": 9.5,
}


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


def _present(value: Any) -> bool:
    return value is not None and value != "" and value != [] and value != {}


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _check_passed(value: Any) -> bool:
    if isinstance(value, dict):
        value = value.get("passed", value.get("status"))
    if isinstance(value, str):
        return value.lower() in {"pass", "passed", "ok", "true"}
    return value is True


def _check_failed(value: Any) -> bool:
    if isinstance(value, dict):
        value = value.get("passed", value.get("status"))
    if isinstance(value, str):
        return value.lower() in {"fail", "failed", "blocked", "false"}
    return value is False


def _inventory_key(value: Any) -> str:
    key = re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")
    return re.sub(r"_(?:table|chart)$", "", key)


def _inventory_statuses(items: Any) -> dict[str, str]:
    statuses: dict[str, str] = {}
    if isinstance(items, dict):
        for key, value in items.items():
            if isinstance(value, dict):
                statuses[_inventory_key(key)] = str(value.get("status") or ("present" if value else "missing"))
            elif isinstance(value, str):
                statuses[_inventory_key(key)] = value
            elif value:
                statuses[_inventory_key(key)] = "present"
    elif isinstance(items, list):
        for item in items:
            if isinstance(item, str):
                statuses[_inventory_key(item)] = "present"
            elif isinstance(item, dict):
                key = item.get("id") or item.get("key") or item.get("name") or item.get("table_id") or item.get("chart_id")
                if key:
                    statuses[_inventory_key(key)] = str(item.get("status") or "present")
    return statuses


def _missing_inventory(required: set[str], items: Any) -> list[str]:
    statuses = _inventory_statuses(items)
    allowed = {"present", "complete", "covered", "insufficient_evidence"}
    return sorted(key for key in required if statuses.get(key, "missing").lower() not in allowed)


def _unexplained_growth_flags(forecast_model: dict[str, Any]) -> list[str]:
    explicit = forecast_model.get("unexplained_abnormal_growth") or []
    flagged = forecast_model.get("abnormal_growth_flags") or forecast_model.get("abnormal_growth") or []
    unexplained = [str(item) for item in explicit]
    for index, item in enumerate(flagged):
        if isinstance(item, dict):
            explained = item.get("explained") is True or _present(item.get("explanation")) or _present(item.get("rationale"))
            if not explained:
                unexplained.append(str(item.get("metric") or item.get("driver") or index))
        elif item:
            unexplained.append(str(item))
    return unexplained


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
    required = ["has_fcff", "has_blend", "has_sensitivity"]
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


def forecast_quality_gate(forecast_model: dict[str, Any]) -> dict[str, Any]:
    """Validate the production forecast artifact against PLAN.md section 9.2."""
    reasons: list[str] = []
    revenue = forecast_model.get("revenue_forecast") or {}

    for dimension in ("by_channel", "by_product_group"):
        decomposition = revenue.get(dimension) or {}
        if not decomposition:
            reasons.append(f"revenue_forecast_{dimension}_missing")
            continue
        missing_drivers = sorted(
            str(name)
            for name, line in decomposition.items()
            if isinstance(line, dict)
            and _present(line.get("forecast"))
            and not _present(line.get("drivers"))
        )
        if not any(isinstance(line, dict) and _present(line.get("forecast")) for line in decomposition.values()):
            reasons.append(f"revenue_forecast_{dimension}_forecast_missing")
        if missing_drivers:
            reasons.append(f"revenue_forecast_{dimension}_drivers_missing:{','.join(missing_drivers)}")

    gross_margin = forecast_model.get("gross_margin_forecast") or {}
    if not _present(gross_margin.get("forecast")):
        reasons.append("gross_margin_forecast_missing")
    if not _present(gross_margin.get("assumptions")):
        reasons.append("gross_margin_rationale_missing")

    opex = forecast_model.get("opex_forecast") or {}
    if not _present(opex.get("selling_expense")) or not _present(opex.get("admin_expense")):
        reasons.append("opex_forecast_missing")
    if not _present(opex.get("assumptions")):
        reasons.append("opex_assumptions_missing")

    working_capital = forecast_model.get("working_capital_forecast") or {}
    missing_wc = [
        key for key in ("receivable_days", "inventory_days", "payable_days")
        if not _present(working_capital.get(key))
    ]
    if missing_wc:
        reasons.append(f"working_capital_assumptions_missing:{','.join(missing_wc)}")

    capex = forecast_model.get("capex_and_depreciation") or {}
    missing_capex = [
        key for key in ("capex_projects", "depreciation")
        if not _present(capex.get(key))
    ]
    if missing_capex:
        reasons.append(f"capex_depreciation_assumptions_missing:{','.join(missing_capex)}")

    debt_cash = forecast_model.get("debt_cash_interest") or {}
    missing_debt_cash = [
        key for key in ("cash", "short_term_debt", "long_term_debt", "interest_expense", "net_borrowing")
        if not _present(debt_cash.get(key))
    ]
    if missing_debt_cash:
        reasons.append(f"debt_cash_assumptions_missing:{','.join(missing_debt_cash)}")

    if not _present(forecast_model.get("eps_forecast")):
        reasons.append("eps_forecast_missing")
    if not _present(forecast_model.get("forecast_financial_summary")):
        reasons.append("forecast_financial_summary_missing")

    checks = forecast_model.get("forecast_quality_checks") or {}
    required_checks = (
        "historical_continuity_check",
        "driver_support_check",
        "margin_sanity_check",
        "balance_sheet_balance_check",
        "cash_flow_consistency_check",
    )
    for check in required_checks:
        if check not in checks:
            reasons.append(f"forecast_quality_check_missing:{check}")
        elif not _check_passed(checks[check]):
            reasons.append(f"forecast_quality_check_failed:{check}")

    unexplained_growth = _unexplained_growth_flags(forecast_model)
    if unexplained_growth:
        reasons.append("unexplained_abnormal_forecast_growth")

    summary = {
        "channel_count": len(revenue.get("by_channel") or {}),
        "product_group_count": len(revenue.get("by_product_group") or {}),
        "quality_checks": checks,
    }
    if reasons:
        return _gate_result("FORECAST_QUALITY_GATE", False, sorted(set(reasons)), summary)
    return pass_gate("FORECAST_QUALITY_GATE", summary)


def valuation_reconciliation_gate(
    valuation: dict[str, Any],
    market_snapshot: dict[str, Any] | None = None,
    *,
    relative_tolerance: float = 0.005,
) -> dict[str, Any]:
    """Reconcile deterministic FCFF/FCFE valuation outputs and recommendation."""
    reasons: list[str] = []
    market_snapshot = market_snapshot or {}
    fcff = valuation.get("fcff") or {}
    fcfe = valuation.get("fcfe") or {}
    assumptions = valuation.get("key_assumptions") or valuation.get("assumptions") or {}
    weighted = valuation.get("weighted_target_price") or valuation.get("blend_dcf") or {}

    required_fcff = (
        "projected_fcff", "pv_of_fcff", "terminal_value", "pv_of_terminal_value",
        "enterprise_value", "cash_and_short_term_investments", "debt", "equity_value",
        "shares_outstanding", "value_per_share",
    )
    required_fcfe = (
        "projected_fcfe", "pv_of_fcfe", "terminal_value", "pv_of_terminal_value",
        "equity_value", "shares_outstanding", "value_per_share",
    )
    fcfe_advisory_reasons: list[str] = []
    missing_fcff = [key for key in required_fcff if not _present(fcff.get(key))]
    missing_fcfe = [key for key in required_fcfe if not _present(fcfe.get(key))]
    if missing_fcff:
        reasons.append(f"fcff_bridge_missing:{','.join(missing_fcff)}")
    if missing_fcfe:
        fcfe_advisory_reasons.append(f"fcfe_bridge_missing:{','.join(missing_fcfe)}")

    fcff_equity = _number(fcff.get("equity_value"))
    fcff_enterprise = _number(fcff.get("enterprise_value"))
    fcff_cash = _number(fcff.get("cash_and_short_term_investments"))
    fcff_debt = _number(fcff.get("debt"))
    if None not in {fcff_equity, fcff_enterprise, fcff_cash, fcff_debt}:
        expected_fcff_equity = fcff_enterprise + fcff_cash - fcff_debt
        if not isclose(fcff_equity, expected_fcff_equity, rel_tol=relative_tolerance, abs_tol=0.01):
            reasons.append("fcff_equity_bridge_not_reconciled")

    for method_name, method in (("fcff", fcff), ("fcfe", fcfe)):
        equity_value = _number(method.get("equity_value"))
        shares = _number(method.get("shares_outstanding"))
        value_per_share = _number(method.get("value_per_share"))
        if equity_value is not None and shares is not None and shares > 0 and value_per_share is not None:
            # Valuation artifacts store equity value in VND bn and shares in mn,
            # so per-share VND is equity_value * 1,000 / shares.
            expected_values = (equity_value / shares, equity_value * 1000 / shares)
            if not any(
                isclose(value_per_share, expected, rel_tol=relative_tolerance, abs_tol=0.01)
                for expected in expected_values
            ):
                target = fcfe_advisory_reasons if method_name == "fcfe" else reasons
                target.append(f"{method_name}_value_per_share_not_reconciled")

    required_wacc = (
        "risk_free_rate", "equity_risk_premium", "beta", "cost_of_equity",
        "cost_of_debt", "tax_rate", "wacc", "terminal_growth",
    )
    missing_wacc = [key for key in required_wacc if not _present(assumptions.get(key))]
    if missing_wacc:
        reasons.append(f"wacc_components_missing:{','.join(missing_wacc)}")
    if not _present(assumptions.get("net_borrowing")):
        fcfe_advisory_reasons.append("fcfe_net_borrowing_assumption_missing")

    wacc = _number(assumptions.get("wacc"))
    terminal_growth = _number(assumptions.get("terminal_growth"))
    if wacc is not None and terminal_growth is not None and terminal_growth >= wacc:
        reasons.append("terminal_growth_not_below_wacc")

    methods = valuation.get("selected_methods") or valuation.get("valuation_methods") or []
    normalized_methods = {str(method).upper() for method in methods}
    if "FCFF" not in normalized_methods:
        reasons.append("fcff_method_missing")
    elif not {"FCFF", "FCFE"}.issubset(normalized_methods):
        fcfe_advisory_reasons.append("fcfe_method_missing")

    weights = valuation.get("method_weights") or {}
    fcff_weight = _number(weights.get("FCFF", weights.get("fcff")))
    fcfe_weight = _number(weights.get("FCFE", weights.get("fcfe")))
    if fcff_weight is None or fcff_weight < 0:
        reasons.append("method_weights_invalid")
    elif fcfe_weight is None or fcfe_weight < 0 or fcff_weight + (fcfe_weight or 0) <= 0:
        fcfe_advisory_reasons.append("fcfe_method_weight_missing")
    else:
        weight_total = fcff_weight + fcfe_weight
        fcff_value = _number(fcff.get("value_per_share"))
        fcfe_value = _number(fcfe.get("value_per_share"))
        target_raw = _number(weighted.get("raw", weighted.get("target_price")))
        if fcff_value is not None and fcfe_value is not None and target_raw is not None:
            expected_target = (fcff_value * fcff_weight + fcfe_value * fcfe_weight) / weight_total
            if not isclose(target_raw, expected_target, rel_tol=relative_tolerance, abs_tol=0.01):
                reasons.append("weighted_target_price_not_reconciled")
        elif target_raw is None:
            reasons.append("weighted_target_price_missing")

    if not _present(valuation.get("sensitivity")):
        reasons.append("valuation_sensitivity_missing")
    if not _present(valuation.get("sanity_checks")):
        reasons.append("valuation_sanity_checks_missing")
    if not _present(valuation.get("approved_assumption_refs")):
        reasons.append("approved_assumption_refs_missing")

    target_raw = _number(weighted.get("raw", weighted.get("target_price")))
    current_price = _number(
        valuation.get("current_price", market_snapshot.get("current_price", market_snapshot.get("price")))
    )
    upside = _number(weighted.get("upside_downside_vs_current_price", valuation.get("upside_downside_vs_current_price")))
    if current_price is None or current_price <= 0:
        reasons.append("current_price_missing_or_invalid")
    if upside is None:
        reasons.append("upside_downside_missing")
    if not _present(valuation.get("recommendation")):
        reasons.append("recommendation_missing")
    if target_raw is not None and current_price is not None and current_price > 0:
        expected_upside = target_raw / current_price - 1
        comparable_upside = upside / 100 if upside is not None and abs(upside) > 2 else upside
        if comparable_upside is None or not isclose(comparable_upside, expected_upside, rel_tol=relative_tolerance, abs_tol=0.001):
            reasons.append("upside_downside_not_reconciled")

        recommendation = str(valuation.get("recommendation") or "").upper()
        expected_recommendation = "BUY" if expected_upside > 0.15 else "SELL" if expected_upside < -0.20 else "HOLD"
        if recommendation and recommendation != expected_recommendation:
            reasons.append("recommendation_not_reconciled")

    sanity_checks = valuation.get("sanity_checks") or {}
    failed_sanity_checks = sorted(key for key, value in sanity_checks.items() if _check_failed(value))
    if failed_sanity_checks:
        reasons.append(f"valuation_sanity_checks_failed:{','.join(failed_sanity_checks)}")

    summary = {
        "fcff_value_per_share": fcff.get("value_per_share"),
        "fcfe_value_per_share": fcfe.get("value_per_share"),
        "weighted_target_price": weighted,
        "current_price": current_price,
    }
    if reasons:
        return _gate_result("VALUATION_RECONCILIATION_GATE", False, sorted(set(reasons)), summary)
    if fcfe_advisory_reasons:
        return _gate_result(
            "VALUATION_RECONCILIATION_GATE",
            True,
            fcfe_advisory_reasons,
            summary,
            severity="warning",
        )
    return pass_gate("VALUATION_RECONCILIATION_GATE", summary)


def report_completeness_gate(report: dict[str, Any]) -> dict[str, Any]:
    """Enforce the minimum report, table, and chart contract from PLAN.md."""
    reasons: list[str] = []
    sections = report.get("sections") or report
    missing_sections = [
        canonical
        for canonical, aliases in _REQUIRED_REPORT_SECTIONS.items()
        if not any(_present(sections.get(alias)) for alias in aliases)
    ]
    if missing_sections:
        reasons.append(f"required_report_sections_missing:{','.join(sorted(missing_sections))}")

    missing_tables = _missing_inventory(_REQUIRED_TABLES, report.get("required_tables"))
    missing_charts = _missing_inventory(_REQUIRED_CHARTS, report.get("required_charts"))
    if missing_tables:
        reasons.append(f"required_report_tables_missing:{','.join(missing_tables)}")
    if missing_charts:
        reasons.append(f"required_report_charts_missing:{','.join(missing_charts)}")

    summary = {
        "required_section_count": len(_REQUIRED_REPORT_SECTIONS),
        "missing_sections": missing_sections,
        "missing_tables": missing_tables,
        "missing_charts": missing_charts,
    }
    if reasons:
        return _gate_result("REPORT_COMPLETENESS_GATE", False, reasons, summary)
    return pass_gate("REPORT_COMPLETENESS_GATE", summary)


def senior_critic_gate(critic_review: dict[str, Any]) -> dict[str, Any]:
    """Convert the Senior Critic Agent rubric into a deterministic publish gate."""
    reasons: list[str] = []
    decision = str(critic_review.get("decision") or "").lower()
    if decision != "pass":
        reasons.append(f"critic_decision_not_pass:{decision or 'missing'}")

    scorecard = critic_review.get("scorecard") or {}
    missing_scores: list[str] = []
    below_threshold: list[str] = []
    missing_explanations: list[str] = []
    for metric, threshold in _CRITIC_MINIMUM_SCORES.items():
        item = scorecard.get(metric)
        score = _number(item.get("score")) if isinstance(item, dict) else _number(item)
        if score is None:
            missing_scores.append(metric)
        elif score < threshold:
            below_threshold.append(f"{metric}={score:g}<{threshold:g}")
        if isinstance(item, dict) and not _present(item.get("explanation")):
            missing_explanations.append(metric)
    if missing_scores:
        reasons.append(f"critic_scores_missing:{','.join(missing_scores)}")
    if below_threshold:
        reasons.append(f"critic_scores_below_threshold:{','.join(below_threshold)}")
    if missing_explanations:
        reasons.append(f"critic_score_explanations_missing:{','.join(missing_explanations)}")

    blocking_findings = sorted(
        str(finding.get("finding_id") or "unidentified_finding")
        for finding in critic_review.get("findings") or []
        if isinstance(finding, dict) and str(finding.get("severity") or "").lower() in {"high", "critical"}
    )
    if blocking_findings:
        reasons.append(f"blocking_critic_findings:{','.join(blocking_findings)}")

    summary = {
        "decision": decision,
        "minimum_scores": _CRITIC_MINIMUM_SCORES,
        "blocking_findings": blocking_findings,
    }
    if reasons:
        return _gate_result("SENIOR_CRITIC_GATE", False, reasons, summary, severity="warning")
    return pass_gate("SENIOR_CRITIC_GATE", summary)


def financial_analyst_gate(financial_summary: dict[str, Any]) -> dict[str, Any]:
    if financial_summary.get("status") == "failed" and not financial_summary.get("payload"):
        return fail_gate("FINANCIAL_ANALYST_GATE", "financial_analyst_failed_no_payload", financial_summary)
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


def package_validation_gate(state: dict[str, Any]) -> dict[str, Any]:
    """Single export-readiness gate aggregating all deterministic package checks."""
    from backend.evaluation.fpts_grade import fpts_grade_gate

    trace = state.get("trace") or []
    valuation = state.get("valuation_outputs") or (state.get("artifacts") or {}).get("valuation") or {}

    tool_perm = tool_permission_gate(trace)
    manifest = artifact_manifest_gate(state)
    formula = formula_trace_gate(valuation)
    evidence = evidence_packet_gate(state)
    fpts_grade = (state.get("gate_results") or {}).get("FPTS_GRADE_GATE") or fpts_grade_gate(state)

    # The export aggregation requires the four sub-gate results to be present in
    # gate_results; inject the ones we just computed so its presence check holds.
    gate_results = dict(state.get("gate_results") or {})
    for sub in (tool_perm, manifest, formula, evidence, fpts_grade):
        gate_results[sub["gate"]] = sub
    export = workflow_export_gate({**state, "gate_results": gate_results})

    sub_gates = [tool_perm, manifest, formula, evidence, fpts_grade, export]
    blocking_reasons: list[str] = []
    for sub in sub_gates:
        if not sub.get("passed"):
            blocking_reasons.extend(sub.get("blocking_reasons") or [f"{sub.get('gate')}_failed"])

    summary = {sub["gate"]: bool(sub.get("passed")) for sub in sub_gates}
    summary["fpts_grade_score"] = (fpts_grade.get("summary") or {}).get("score")
    summary["fpts_grade_decision"] = (fpts_grade.get("summary") or {}).get("decision")
    if blocking_reasons:
        return _gate_result("PACKAGE_VALIDATION_GATE", False, sorted(set(blocking_reasons)), summary, severity="warning")
    return pass_gate("PACKAGE_VALIDATION_GATE", summary)


def workflow_export_gate(state: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
    gate_results = state.get("gate_results") or {}
    blocking_reasons: list[str] = []
    required_gates = {
        "TOOL_PERMISSION_GATE",
        "ARTIFACT_MANIFEST_GATE",
        "FORMULA_TRACE_GATE",
        "EVIDENCE_PACKET_GATE",
    }
    missing_required = sorted(name for name in required_gates if name not in gate_results)
    if missing_required:
        blocking_reasons.append(f"required_harness_gate_missing:{','.join(missing_required)}")
    failed = [name for name, gate in gate_results.items() if isinstance(gate, dict) and gate.get("passed") is False]
    if failed:
        blocking_reasons.append(f"upstream_gate_failed:{','.join(failed)}")
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
    if valuation and not (state.get("artifacts") or {}).get("research_lock"):
        blocking_reasons.append("valuation_lock_missing")
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
