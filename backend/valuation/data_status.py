"""Module-level readiness policy for valuation input packs."""
from __future__ import annotations

from typing import Any, Literal

from backend.facts.normalizer import FactTable
from backend.valuation.required_metrics import (
    EV_EBITDA_REQUIRED,
    FCFE_REQUIRED,
    FCFF_REQUIRED,
    HARD_BLOCK_FACTS,
    PE_SANITY_REQUIRED,
    RATIO_REQUIRED,
)

ReadinessStatus = Literal[
    "ready",
    "ready_with_policy",
    "ready_or_no_action_recorded",
    "draft_publishable",
    "warning",
    "blocked",
]


def fact_available(fact_table: FactTable, metric: str, periods: list[str]) -> bool:
    """Return True when a metric has a real value in at least one requested period."""
    for period in periods:
        entry = fact_table.get(metric, {}).get(period)
        if entry is not None:
            value = getattr(entry, "value", None)
            if value is None and isinstance(entry, dict):
                value = entry.get("value")
            if value is not None:
                return True
    return False


def missing_facts(fact_table: FactTable, metrics: set[str], periods: list[str]) -> list[str]:
    return sorted(metric for metric in metrics if not fact_available(fact_table, metric, periods))


def _hard_block_missing(fact_table: FactTable, periods: list[str]) -> list[str]:
    missing: list[str] = []
    for requirement in HARD_BLOCK_FACTS:
        if isinstance(requirement, tuple):
            if not any(fact_available(fact_table, metric, periods) for metric in requirement):
                missing.append(" or ".join(requirement))
        elif not fact_available(fact_table, requirement, periods):
            missing.append(requirement)
    return missing


def _debt_policy_publishable(debt_policy: dict[str, Any]) -> bool:
    method = str(debt_policy.get("method") or debt_policy.get("forecast_method") or "").lower()
    approved = bool(debt_policy.get("analyst_approved") or debt_policy.get("approved"))
    publishable = bool(debt_policy.get("publishable"))
    if method in {"zero_debt_policy", "cfs_net_borrowing"}:
        return publishable or approved
    if method in {"manual_debt_path", "manual_override"}:
        return publishable and approved
    return False


def build_module_readiness(
    *,
    fact_table: FactTable,
    periods: list[str],
    market: dict[str, Any],
    peers: dict[str, Any],
    debt_policy: dict[str, Any],
    corporate_actions: dict[str, Any],
    working_capital_policy: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Build module-level readiness with hard/soft gating separated."""
    readiness: dict[str, dict[str, Any]] = {}

    hard_missing = _hard_block_missing(fact_table, periods)
    price_present = market.get("price") is not None
    shares_present = (
        market.get("shares_outstanding") is not None
        or fact_available(fact_table, "shares_outstanding.ending", periods)
        or fact_available(fact_table, "shares_outstanding.weighted_avg", periods)
    )

    readiness["reported_facts"] = {
        "status": "ready" if not hard_missing else "blocked",
        "missing_fields": hard_missing,
    }

    ratio_missing = missing_facts(fact_table, RATIO_REQUIRED, periods)
    readiness["ratios"] = {
        "status": "ready" if not ratio_missing else "warning",
        "missing_fields": ratio_missing,
    }

    fcff_missing = missing_facts(fact_table, FCFF_REQUIRED, periods)
    wc_policy_ready = bool(working_capital_policy) and working_capital_policy.get("status") != "missing"
    readiness["fcff"] = {
        "status": "ready" if not fcff_missing and price_present and shares_present else "blocked",
        "missing_fields": fcff_missing
        + ([] if price_present else ["price"])
        + ([] if shares_present else ["shares_outstanding"]),
        "working_capital_policy": "available" if wc_policy_ready else "not_provided",
    }

    fcfe_missing = missing_facts(fact_table, FCFE_REQUIRED, periods)
    debt_ready = _debt_policy_publishable(debt_policy)
    readiness["fcfe"] = {
        "status": "ready_with_policy" if not fcfe_missing and debt_ready and shares_present else "blocked",
        "missing_fields": fcfe_missing + ([] if shares_present else ["shares_outstanding"]),
        "debt_policy_status": "publishable" if debt_ready else "not_publishable",
    }

    pe_missing = missing_facts(fact_table, PE_SANITY_REQUIRED, periods)
    peer_pe_ready = peers.get("peer_pe_median") is not None
    readiness["pe_sanity"] = {
        "status": "ready" if not pe_missing and price_present and peer_pe_ready else "warning",
        "missing_fields": pe_missing
        + ([] if price_present else ["price"])
        + ([] if peer_pe_ready else ["peer_pe_median"]),
    }

    ev_missing = missing_facts(fact_table, EV_EBITDA_REQUIRED, periods)
    peer_ev_ready = peers.get("peer_ev_ebitda_median") is not None
    readiness["ev_ebitda"] = {
        "status": "ready" if not ev_missing and price_present and shares_present and peer_ev_ready else "warning",
        "missing_fields": ev_missing
        + ([] if price_present else ["price"])
        + ([] if shares_present else ["shares_outstanding"])
        + ([] if peer_ev_ready else ["peer_ev_ebitda_median"]),
    }

    ca_status = corporate_actions.get("status") or "no_action_recorded"
    readiness["corporate_action"] = {
        "status": "ready_or_no_action_recorded",
        "corporate_action_status": ca_status,
    }

    report_blocked = readiness["reported_facts"]["status"] == "blocked" or not price_present or not shares_present
    readiness["report"] = {
        "status": "blocked" if report_blocked else "draft_publishable",
        "missing_fields": hard_missing
        + ([] if price_present else ["price"])
        + ([] if shares_present else ["shares_outstanding"]),
    }

    return readiness
