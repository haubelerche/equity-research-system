"""Deterministic institutional report-quality gates and scoring."""
from __future__ import annotations

from typing import Any

from backend.evaluation.citation_coverage import is_vague_source
from backend.evaluation.governance import (
    decomposition_issues,
    forecast_sanity_issues,
    valuation_reproduction_issues,
    valid_decomposition_lines,
)
from backend.harness.gates import _gate_result, pass_gate


def _rows(forecast: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        row for row in forecast.get("forecast_years", [])
        if isinstance(row, dict)
    ]


def _normalized_forecast(forecast: dict[str, Any]) -> dict[str, Any]:
    deterministic = forecast.get("deterministic_forecast")
    if not isinstance(deterministic, dict):
        return forecast
    return {
        **deterministic,
        "pharma_driver_model": forecast.get("pharma_driver_model")
        or deterministic.get("pharma_driver_model")
        or {},
    }


def _missing(payload: dict[str, Any], field: str) -> bool:
    value = payload.get(field)
    return value is None or value == "" or value == [] or value == {}


def _growth(previous: Any, current: Any) -> float | None:
    if not isinstance(previous, (int, float)) or not isinstance(current, (int, float)):
        return None
    if previous == 0:
        return None
    return current / previous - 1


def _is_quantitative_claim(claim: dict[str, Any]) -> bool:
    quantitative = claim.get("quantitative")
    if isinstance(quantitative, bool):
        return quantitative
    return str(claim.get("claim_type") or "").lower() in {"quantitative", "valuation"}


def financial_model_integrity_gate(
    forecast: dict[str, Any],
    valuation: dict[str, Any],
) -> dict[str, Any]:
    reasons: list[str] = []
    forecast = _normalized_forecast(forecast)
    rows = _rows(forecast)

    for row in rows:
        label = str(row.get("label") or "forecast_period")
        required_bs = ("total_assets", "equity", "total_debt", "cash", "other_liabilities")
        missing = [field for field in required_bs if row.get(field) is None]
        if missing:
            reasons.append(f"balance_sheet_incomplete:{label}:{','.join(missing)}")
        elif abs(
            float(row["total_assets"])
            - float(row["equity"])
            - float(row["total_debt"])
            - float(row["other_liabilities"])
        ) > 0.5:
            reasons.append(f"balance_sheet_not_reconciled:{label}")
        if all(row.get(field) is not None for field in ("total_debt", "cash", "net_debt")):
            if abs(float(row["net_debt"]) - (float(row["total_debt"]) - float(row["cash"]))) > 0.5:
                reasons.append(f"net_debt_not_reconciled:{label}")

        if all(row.get(field) is not None for field in ("net_income", "eps", "diluted_shares")):
            implied_eps = float(row["net_income"]) * 1_000 / float(row["diluted_shares"])
            if abs(float(row["eps"]) - implied_eps) / max(abs(implied_eps), 1) > 0.02:
                reasons.append(f"eps_not_reconciled:{label}")

    for previous, current in zip(rows, rows[1:]):
        ni_growth = _growth(previous.get("net_income"), current.get("net_income"))
        eps_growth = _growth(previous.get("eps"), current.get("eps"))
        share_growth = _growth(previous.get("diluted_shares"), current.get("diluted_shares"))
        if ni_growth is not None and eps_growth is not None:
            expected_gap = abs(share_growth or 0.0)
            if abs(eps_growth - ni_growth) > expected_gap + 0.03:
                reasons.append(f"eps_growth_not_explained_by_shares:{current.get('label')}")

    current_price = (
        (valuation.get("blend_dcf") or {}).get("current_price_vnd")
        or valuation.get("current_price_vnd")
        or valuation.get("current_price")
    )
    for row in rows:
        dividend = row.get("cash_dividend") or row.get("dps")
        dividend_yield = row.get("dividend_yield")
        if isinstance(dividend, (int, float)) and dividend > 0 and dividend_yield == 0:
            reasons.append(f"dividend_yield_total_return_inconsistent:{row.get('label')}")
        if (
            isinstance(dividend, (int, float))
            and dividend > 0
            and isinstance(dividend_yield, (int, float))
            and isinstance(current_price, (int, float))
            and current_price > 0
            and abs(dividend_yield - dividend / current_price) > 0.005
        ):
            reasons.append(f"dividend_yield_not_reconciled:{row.get('label')}")

    fcff = valuation.get("fcff") or {}
    required_fcff = (
        "fcff_table", "sum_pv_fcff", "terminal_value", "pv_terminal_value",
        "enterprise_value", "net_debt_bridge", "equity_value", "shares_mn",
        "target_price_vnd", "wacc_breakdown",
    )
    missing_fcff = [field for field in required_fcff if _missing(fcff, field)]
    if missing_fcff:
        reasons.append(f"fcff_bridge_incomplete:{','.join(missing_fcff)}")
    net_debt_bridge = fcff.get("net_debt_bridge") or {}
    if net_debt_bridge.get("status") == "blocked":
        reasons.append("fcff_net_debt_bridge_blocked")

    return _gate_result(
        "FINANCIAL_MODEL_INTEGRITY_GATE",
        not reasons,
        sorted(set(reasons)),
        {"forecast_periods": len(rows), "issues": len(set(reasons))},
    )


def forecast_reasonableness_gate(forecast: dict[str, Any]) -> dict[str, Any]:
    forecast = _normalized_forecast(forecast)
    reasons = forecast_sanity_issues(forecast)
    driver_model = forecast.get("pharma_driver_model") or {}
    revenue = driver_model.get("revenue") or {}
    revenue_forecast = {
        "by_channel": revenue.get("by_channel") or {},
        "by_product_group": revenue.get("by_product_group") or {},
        "company_growth": revenue.get("aggregate_revenue") or {},
    }
    reasons.extend(decomposition_issues(revenue_forecast))
    channel_count = len(valid_decomposition_lines(revenue_forecast["by_channel"]))
    product_count = len(valid_decomposition_lines(revenue_forecast["by_product_group"]))

    return _gate_result(
        "FORECAST_REASONABLENESS_GATE",
        not reasons,
        sorted(set(reasons)),
        {"channel_count": channel_count, "product_group_count": product_count},
    )


def company_research_depth_gate(company_research_pack: dict[str, Any]) -> dict[str, Any]:
    coverage = company_research_pack.get("coverage") or {}
    ratio = coverage.get("coverage_ratio")
    required = tuple(coverage.get("required_topic_names") or (
        "revenue_by_channel",
        "revenue_by_product_group",
        "regulatory_and_gmp_status",
        "api_exposure",
        "peer_positioning",
        "catalysts",
        "risks",
    ))
    def covered(field: str) -> bool:
        value = company_research_pack.get(field)
        if isinstance(value, list):
            return bool(value)
        return bool(value) and any(
            isinstance(record, dict)
            and record.get("status") in {"observed", "approved_estimate"}
            and record.get("evidence_refs")
            for record in value.values()
        )

    missing = [field for field in required if not covered(field)]
    reasons = [f"company_research_pack_missing:{','.join(missing)}"] if missing else []
    if not company_research_pack.get("source_map"):
        reasons.append("company_research_pack_source_map_missing")
    return _gate_result(
        "COMPANY_RESEARCH_DEPTH_GATE",
        not reasons,
        reasons,
        {"coverage_ratio": ratio, "missing_required_topics": missing},
    )


def analyst_insight_gate(company_research_pack: dict[str, Any]) -> dict[str, Any]:
    insights = company_research_pack.get("analyst_insights") or []
    ready = [
        insight for insight in insights
        if isinstance(insight, dict) and insight.get("status") == "ready"
    ]
    reasons: list[str] = []
    if not insights:
        reasons.append("analyst_insights_missing")
    elif len(ready) != len(insights):
        reasons.append(f"analyst_insights_incomplete:{len(ready)}/{len(insights)}")
    return _gate_result(
        "ANALYST_INSIGHT_GATE",
        not reasons,
        reasons,
        {"insight_count": len(insights), "ready_insight_count": len(ready)},
    )


def professional_presentation_gate(report: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    sections = report.get("sections") or {}
    required_sections = (
        "cover_investment_summary",
        "recent_financial_performance",
        "driver_based_forecast",
        "valuation_and_recommendation",
        "risks_and_monitoring_factors",
        "appendix",
    )
    missing_sections = [
        section for section in required_sections if not sections.get(section)
    ]
    if missing_sections:
        reasons.append(f"professional_sections_missing:{','.join(missing_sections)}")

    def _spec_items(specs: Any, collection_key: str) -> list[dict[str, Any]]:
        if isinstance(specs, list):
            return [item for item in specs if isinstance(item, dict)]
        if isinstance(specs, dict):
            nested = specs.get(collection_key)
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, dict)]
            return [
                item for item in specs.values()
                if isinstance(item, dict)
                and (
                    item.get("id")
                    or item.get("key")
                    or item.get("name")
                    or item.get("chart_id")
                    or item.get("table_id")
                )
            ]
        return []

    chart_specs = _spec_items(report.get("chart_specs"), "charts")
    table_specs = _spec_items(report.get("table_specs"), "tables")
    if not chart_specs:
        reasons.append("numbered_sourced_charts_missing")
    if not table_specs:
        reasons.append("numbered_sourced_tables_missing")
    def has_source_map(item: dict[str, Any]) -> bool:
        refs = item.get("source_artifact_refs")
        source_map = item.get("source_map")
        return bool(refs) or (
            isinstance(source_map, dict)
            and any(bool(value) for value in source_map.values())
        )

    for kind, specs in (("chart", chart_specs), ("table", table_specs)):
        invalid = [
            str(
                item.get("id")
                or item.get("key")
                or item.get("name")
                or item.get(f"{kind}_id")
                or index
            )
            for index, item in enumerate(specs)
            if not (
                item.get("id")
                or item.get("key")
                or item.get("name")
                or item.get(f"{kind}_id")
            )
            or not (item.get("title") or item.get(f"{kind}_title"))
            or not (item.get("source") or item.get("data_source"))
        ]
        if invalid:
            reasons.append(f"{kind}_metadata_incomplete:{','.join(invalid[:10])}")
        missing_source_maps = [
            str(item.get("id") or item.get(f"{kind}_id") or index)
            for index, item in enumerate(specs)
            if not has_source_map(item)
        ]
        if missing_source_maps:
            reasons.append(f"{kind}_source_map_missing:{','.join(missing_source_maps[:10])}")

    return _gate_result(
        "PROFESSIONAL_PRESENTATION_GATE",
        not reasons,
        sorted(set(reasons)),
        {
            "section_count": len(sections) if isinstance(sections, dict) else 0,
            "chart_count": len(chart_specs),
            "table_count": len(table_specs),
        },
    )


def valuation_completeness_gate(
    valuation: dict[str, Any],
    report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    reasons: list[str] = []
    report = report or {}
    selected = {str(item).upper() for item in valuation.get("selected_methods") or []}
    report_text = str(report).upper()
    mentions_fcfe = "FCFE" in report_text or "FCFE" in selected
    fcfe = valuation.get("fcfe") or {}
    if mentions_fcfe and not fcfe.get("fcfe_table"):
        reasons.append("report_mentions_missing_valuation_method:FCFE")

    bridge = valuation.get("valuation_bridge") or build_valuation_bridge(valuation)
    required_bridge = ("method", "forecast_years", "wacc", "fcff_table", "terminal_value", "equity_bridge")
    missing = [field for field in required_bridge if not bridge.get(field)]
    if missing:
        reasons.append(f"valuation_bridge_incomplete:{','.join(missing)}")

    wacc = bridge.get("wacc") or {}
    required_wacc = (
        "risk_free_rate", "beta", "equity_risk_premium", "cost_of_equity",
        "pre_tax_cost_of_debt", "tax_rate", "target_debt_weight",
        "target_equity_weight", "wacc",
    )
    missing_wacc = [field for field in required_wacc if _missing(wacc, field)]
    if missing_wacc:
        reasons.append(f"wacc_decomposition_incomplete:{','.join(missing_wacc)}")

    equity_bridge = bridge.get("equity_bridge") or {}
    required_equity_bridge = (
        "enterprise_value", "cash_and_equivalents", "debt", "equity_value",
        "diluted_shares", "target_price",
    )
    missing_equity_bridge = [
        field for field in required_equity_bridge if _missing(equity_bridge, field)
    ]
    if missing_equity_bridge:
        reasons.append(
            f"ev_to_equity_bridge_incomplete:{','.join(missing_equity_bridge)}"
        )
    reasons.extend(valuation_reproduction_issues(valuation))

    tv_share = (bridge.get("terminal_value") or {}).get("terminal_value_share_of_ev")
    warnings = ["terminal_value_share_of_ev_above_70pct"] if isinstance(tv_share, (int, float)) and tv_share > 0.70 else []
    result = _gate_result(
        "VALUATION_COMPLETENESS_GATE",
        not reasons,
        sorted(set(reasons)),
        {"terminal_value_share_of_ev": tv_share, "warnings": warnings},
    )
    if warnings:
        result["issues"].extend({
            "issue_id": f"VALUATION_COMPLETENESS_GATE:WARN_{index}",
            "severity": "warning",
            "message": warning,
            "blocking": False,
        } for index, warning in enumerate(warnings))
    return result


def citation_coverage_gate(report: dict[str, Any]) -> dict[str, Any]:
    claims = report.get("claims") or []
    quantitative = [
        claim for claim in claims
        if isinstance(claim, dict) and _is_quantitative_claim(claim)
    ]
    unsupported: list[str] = []
    generic: list[str] = []
    for index, claim in enumerate(quantitative):
        claim_id = str(claim.get("claim_id") or index)
        has_lineage = bool(
            claim.get("fact_id")
            or claim.get("artifact_id")
            or claim.get("calculation_path")
            or claim.get("evidence_refs")
            or claim.get("supporting_refs")
            or claim.get("source_artifact_refs")
        )
        if not has_lineage:
            unsupported.append(claim_id)
        source = str(claim.get("source") or claim.get("source_title") or "")
        if source and is_vague_source(source):
            generic.append(claim_id)
    reasons: list[str] = []
    if unsupported:
        reasons.append(f"citation_coverage_below_threshold:{len(quantitative)-len(unsupported)}/{len(quantitative)}")
    if generic:
        reasons.append(f"generic_citation_only:{','.join(generic[:10])}")
    return _gate_result(
        "CITATION_COVERAGE_GATE",
        not reasons,
        reasons,
        {
            "quantitative_claims": len(quantitative),
            "claims_with_lineage": len(quantitative) - len(unsupported),
            "coverage_ratio": 1.0 if not quantitative else (len(quantitative) - len(unsupported)) / len(quantitative),
        },
    )


def recommendation_consistency_gate(
    report: dict[str, Any],
    approval_status: str | None,
) -> dict[str, Any]:
    recommendation = str(report.get("recommendation") or "").upper()
    target_visible = report.get("target_price_vnd") is not None or report.get("target_price") is not None
    official = recommendation in {"BUY", "HOLD", "SELL", "MUA", "NẮM GIỮ", "BÁN"}
    reasons: list[str] = []
    if approval_status != "approved" and official:
        reasons.append("recommendation_visible_before_approval")
    if approval_status != "approved" and target_visible and report.get("publication_status") in {"approved", "published"}:
        reasons.append("target_price_published_before_approval")
    return _gate_result(
        "RECOMMENDATION_CONSISTENCY_GATE",
        not reasons,
        reasons,
        {"approval_status": approval_status, "visible_recommendation": recommendation},
    )


def build_pharma_driver_model(forecast: dict[str, Any]) -> dict[str, Any]:
    forecast = _normalized_forecast(forecast)
    drivers = forecast.get("drivers") or {}
    return {
        "schema_version": "1.0",
        "revenue": {
            "by_channel": forecast.get("revenue_by_channel") or {},
            "by_product_group": forecast.get("revenue_by_product_group") or {},
            "aggregate_growth": drivers.get("revenue_growth"),
        },
        "gross_margin": {
            "product_mix_effect": drivers.get("product_mix_effect"),
            "api_cost_effect": drivers.get("api_cost_effect"),
            "fx_effect": drivers.get("fx_effect"),
            "pricing_effect": drivers.get("pricing_effect"),
            "aggregate_assumption": drivers.get("gross_margin"),
        },
        "opex": {
            "selling_expense_ratio": drivers.get("selling_expense_ratio"),
            "admin_expense_ratio": drivers.get("admin_expense_ratio"),
            "combined_sga_ratio": drivers.get("sga_to_revenue"),
            "one_off_adjustments": drivers.get("one_off_adjustments") or [],
        },
        "capex_depreciation": {
            "capex_plan": drivers.get("capex_plan"),
            "capex_to_revenue": drivers.get("capex_to_revenue"),
            "depreciation_to_revenue": drivers.get("depreciation_to_revenue"),
        },
        "working_capital": forecast.get("working_capital_schedule") or {},
        "tax_and_financing": {
            "effective_tax_rate": drivers.get("effective_tax_rate"),
            "debt_schedule": forecast.get("debt_schedule") or {},
            "cost_of_debt": drivers.get("cost_of_debt"),
        },
    }


def build_valuation_bridge(valuation: dict[str, Any]) -> dict[str, Any]:
    fcff = valuation.get("fcff") or {}
    ev = fcff.get("enterprise_value")
    pv_tv = fcff.get("pv_terminal_value")
    net_debt_bridge = fcff.get("net_debt_bridge") or {}
    return {
        "schema_version": "1.0",
        "method": "FCFF",
        "forecast_years": [row.get("label") for row in fcff.get("fcff_table") or [] if isinstance(row, dict)],
        "wacc": {
            **(valuation.get("key_assumptions") or {}),
            **(fcff.get("wacc_breakdown") or {}),
            "wacc": fcff.get("wacc"),
        },
        "fcff_table": fcff.get("fcff_table") or [],
        "terminal_value": {
            "terminal_growth": fcff.get("terminal_growth"),
            "terminal_value": fcff.get("terminal_value"),
            "pv_terminal_value": pv_tv,
            "terminal_value_share_of_ev": pv_tv / ev if isinstance(pv_tv, (int, float)) and isinstance(ev, (int, float)) and ev else None,
        },
        "equity_bridge": {
            "enterprise_value": ev,
            "cash_and_equivalents": net_debt_bridge.get("cash"),
            "short_term_investments": net_debt_bridge.get("short_term_investments"),
            "debt": net_debt_bridge.get("total_debt"),
            "minority_interest": net_debt_bridge.get("minority_interest"),
            "net_debt": fcff.get("net_debt"),
            "equity_value": fcff.get("equity_value"),
            "diluted_shares": fcff.get("shares_mn"),
            "target_price": fcff.get("target_price_vnd"),
        },
    }


_WEIGHTS = {
    "data_correctness": 25,
    "financial_model_integrity": 25,
    "domain_depth": 15,
    "valuation_transparency": 15,
    "citation_quality": 10,
    "professional_presentation": 10,
}


def evaluate_report_quality(
    *,
    forecast: dict[str, Any],
    valuation: dict[str, Any],
    report: dict[str, Any],
    approval_status: str | None = None,
    company_research_pack: dict[str, Any] | None = None,
) -> dict[str, Any]:
    gates = {
        "financial_model_integrity": financial_model_integrity_gate(forecast, valuation),
        "forecast_reasonableness": forecast_reasonableness_gate(forecast),
        "company_research_depth": company_research_depth_gate(company_research_pack or {}),
        "analyst_insight": analyst_insight_gate(company_research_pack or {}),
        "valuation_completeness": valuation_completeness_gate(valuation, report),
        "citation_coverage": citation_coverage_gate(report),
        "recommendation_consistency": recommendation_consistency_gate(report, approval_status),
        "professional_presentation": professional_presentation_gate(report),
    }
    section_scores = {
        "data_correctness": _WEIGHTS["data_correctness"] if gates["financial_model_integrity"]["passed"] else 0,
        "financial_model_integrity": _WEIGHTS["financial_model_integrity"] if gates["financial_model_integrity"]["passed"] else 0,
        "domain_depth": (
            _WEIGHTS["domain_depth"]
            if (
                gates["forecast_reasonableness"]["passed"]
                and gates["company_research_depth"]["passed"]
                and gates["analyst_insight"]["passed"]
            )
            else 0
        ),
        "valuation_transparency": _WEIGHTS["valuation_transparency"] if gates["valuation_completeness"]["passed"] else 0,
        "citation_quality": _WEIGHTS["citation_quality"] if gates["citation_coverage"]["passed"] else 0,
        "professional_presentation": (
            _WEIGHTS["professional_presentation"]
            if (
                gates["recommendation_consistency"]["passed"]
                and gates["professional_presentation"]["passed"]
            )
            else 0
        ),
    }
    score = sum(section_scores.values())
    failed = [name for name, gate in gates.items() if not gate["passed"]]
    decision = "allow_export" if score >= 85 and not failed else "draft_only" if score >= 70 else "block_export"
    return {
        "rubric": "report_quality_v1",
        "score": score,
        "maximum_score": 100,
        "decision": decision,
        "passed": decision == "allow_export",
        "section_scores": section_scores,
        "failed_gates": failed,
        "gates": gates,
    }


def report_quality_gate(state: dict[str, Any]) -> dict[str, Any]:
    artifacts = state.get("artifacts") or {}
    forecast = artifacts.get("forecast_model") or {}
    valuation = state.get("valuation_outputs") or artifacts.get("valuation") or {}
    report = (
        artifacts.get("report_candidate_model")
        or artifacts.get("review_passed_report_model")
        or artifacts.get("publishable_final_report_model")
        or state.get("draft_report")
        or artifacts.get("report_draft")
        or {}
    )
    company_research_pack = artifacts.get("company_research_pack") or {}
    approval_status = (state.get("policy") or {}).get("approval_status") or (
        "approved" if state.get("status") == "approved" else None
    )
    result = evaluate_report_quality(
        forecast=forecast,
        valuation=valuation,
        report=report,
        approval_status=approval_status,
        company_research_pack=company_research_pack,
    )
    if result["passed"]:
        return pass_gate("REPORT_QUALITY_GATE", result)
    reasons = [
        reason
        for gate in result["gates"].values()
        for reason in gate.get("blocking_reasons", [])
    ]
    return _gate_result("REPORT_QUALITY_GATE", False, sorted(set(reasons)), result, severity="warning")
