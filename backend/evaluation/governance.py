"""Shared deterministic governance rules for client-final research artifacts."""
from __future__ import annotations

from math import isclose
from typing import Any


AGGREGATE_KEYS = {
    "all",
    "all_channels",
    "all_products",
    "aggregate",
    "aggregate_only",
    "unavailable",
    "unknown",
}
NON_FINAL_STATUSES = {
    "aggregate_only",
    "insufficient_evidence",
    "missing",
    "unavailable",
    "unknown",
}


def is_real_decomposition_line(name: str, line: Any) -> bool:
    """Return True only for a sourced, driver-backed non-aggregate forecast line."""
    if str(name).strip().lower() in AGGREGATE_KEYS or not isinstance(line, dict):
        return False
    if str(line.get("status") or "").strip().lower() in NON_FINAL_STATUSES:
        return False
    forecast = line.get("forecast")
    drivers = line.get("drivers")
    evidence = line.get("evidence_refs") or line.get("source_artifact_refs")
    assumption = line.get("approved_assumption_ref") or line.get("approved_assumption_refs")
    return bool(forecast) and bool(drivers) and bool(evidence or assumption)


def valid_decomposition_lines(decomposition: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(decomposition, dict):
        return {}
    return {
        str(name): line
        for name, line in decomposition.items()
        if is_real_decomposition_line(str(name), line)
    }


def decomposition_issues(
    revenue_forecast: dict[str, Any],
    *,
    require_channels: int = 2,
    require_product_groups: int = 1,
) -> list[str]:
    issues: list[str] = []
    channels = valid_decomposition_lines(revenue_forecast.get("by_channel"))
    products = valid_decomposition_lines(revenue_forecast.get("by_product_group"))
    if len(channels) < require_channels:
        issues.append("pharma_driver_channels_insufficient")
    if len(products) < require_product_groups:
        issues.append("pharma_driver_product_groups_missing")
    issues.extend(_decomposition_reconciliation_issues(revenue_forecast, "by_channel", channels))
    issues.extend(_decomposition_reconciliation_issues(revenue_forecast, "by_product_group", products))
    return issues


def _decomposition_reconciliation_issues(
    revenue_forecast: dict[str, Any],
    dimension: str,
    lines: dict[str, dict[str, Any]],
) -> list[str]:
    aggregate = revenue_forecast.get("company_growth") or revenue_forecast.get("aggregate_revenue")
    if not isinstance(aggregate, dict) or not lines:
        return []
    issues: list[str] = []
    for period, expected in aggregate.items():
        values = [
            (line.get("forecast") or {}).get(period)
            for line in lines.values()
            if isinstance(line.get("forecast"), dict)
        ]
        if not isinstance(expected, (int, float)) or not values:
            continue
        if not all(isinstance(value, (int, float)) for value in values):
            issues.append(f"revenue_decomposition_incomplete:{dimension}:{period}")
            continue
        if not isclose(sum(values), float(expected), rel_tol=0.005, abs_tol=0.5):
            issues.append(f"revenue_decomposition_not_reconciled:{dimension}:{period}")
    return issues


def is_valid_bridge(bridge: Any) -> bool:
    """A bridge must explain and reconcile numeric line-item deltas with evidence."""
    if not isinstance(bridge, dict):
        return False
    if not bridge.get("from_period") or not bridge.get("to_period"):
        return False
    items = bridge.get("line_items")
    if not isinstance(items, list) or not items:
        return False
    deltas: list[float] = []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("delta"), (int, float)):
            return False
        if not item.get("reason") or not (item.get("evidence_refs") or item.get("approved_assumption_refs")):
            return False
        deltas.append(float(item["delta"]))
    total = bridge.get("total_delta")
    return isinstance(total, (int, float)) and isclose(
        sum(deltas), float(total), rel_tol=0.005, abs_tol=0.5
    )


def has_valid_bridge(payload: dict[str, Any], *names: str) -> bool:
    return any(is_valid_bridge(payload.get(name)) for name in names)


def forecast_sanity_issues(forecast: dict[str, Any]) -> list[str]:
    """Return shared forecast issue codes used by all client-final gates."""
    rows = [row for row in forecast.get("forecast_years", []) if isinstance(row, dict)]
    issues: list[str] = []
    profit_bridge = has_valid_bridge(forecast, "profit_bridge", "margin_bridge")
    operating_bridge = has_valid_bridge(
        forecast, "operating_leverage_bridge", "margin_bridge", "sga_bridge"
    )
    for previous, current in zip(rows, rows[1:]):
        label = str(current.get("label") or "forecast_period")
        revenue_growth = _growth(previous.get("revenue"), current.get("revenue"))
        profit_growth = _growth(previous.get("net_income"), current.get("net_income"))
        eps_growth = _growth(previous.get("eps"), current.get("eps"))
        if revenue_growth is not None and revenue_growth >= 0:
            threshold = max(0.15, 2 * revenue_growth)
            if profit_growth is not None and profit_growth > threshold and not profit_bridge:
                issues.append(f"profit_growth_requires_bridge:{label}")
            if eps_growth is not None and eps_growth > threshold and not profit_bridge:
                issues.append(f"eps_growth_requires_bridge:{label}")

        ebit_delta = _delta(previous.get("ebit_margin"), current.get("ebit_margin"))
        net_delta = _delta(previous.get("net_margin"), current.get("net_margin"))
        gross_delta = _delta(previous.get("gross_margin"), current.get("gross_margin"))
        if (
            ebit_delta is not None
            and ebit_delta > 0.03
            and (gross_delta is None or gross_delta < ebit_delta - 0.01)
            and not operating_bridge
        ):
            issues.append(f"ebit_margin_jump_without_gross_margin_support:{label}")
        if net_delta is not None and net_delta > 0.03 and not profit_bridge:
            issues.append(f"net_margin_jump_requires_bridge:{label}")
        if (
            revenue_growth is not None
            and revenue_growth > 0
            and isinstance(previous.get("sga"), (int, float))
            and isinstance(current.get("sga"), (int, float))
            and abs(float(current["sga"])) < abs(float(previous["sga"]))
            and not operating_bridge
        ):
            issues.append(f"sga_decline_requires_bridge:{label}")
    return sorted(set(issues))


def valuation_reproduction_issues(valuation: dict[str, Any]) -> list[str]:
    """Recompute per-method and weighted target prices from printed artifacts."""
    issues: list[str] = []
    for method_name in ("fcff", "fcfe"):
        method = valuation.get(method_name) or {}
        equity = _number(method.get("equity_value"))
        shares = _number(method.get("shares_outstanding") or method.get("shares_mn"))
        target = _number(method.get("value_per_share") or method.get("target_price_vnd"))
        if equity is not None and shares and target is not None:
            expected = equity * 1_000 / shares
            if not isclose(target, expected, rel_tol=0.005, abs_tol=1.0):
                issues.append(f"{method_name}_target_price_not_reproducible")

    selected = [str(item).upper() for item in valuation.get("selected_methods") or []]
    weights = valuation.get("method_weights") or {}
    weighted = valuation.get("weighted_target_price") or valuation.get("blend_dcf") or {}
    target = _number(
        weighted.get("raw")
        or weighted.get("target_price_vnd")
        or weighted.get("blended_price")
        or weighted.get("target_price_dcf_vnd")
    )
    if selected and weights:
        parts: list[float] = []
        total_weight = 0.0
        for name in selected:
            method = valuation.get(name.lower()) or {}
            price = _number(method.get("value_per_share") or method.get("target_price_vnd"))
            weight = _number(weights.get(name) or weights.get(name.lower()))
            if price is None or weight is None:
                issues.append(f"valuation_method_input_missing:{name}")
                continue
            parts.append(price * weight)
            total_weight += weight
        if parts and total_weight:
            expected = sum(parts) / total_weight
            if target is None or not isclose(target, expected, rel_tol=0.005, abs_tol=1.0):
                issues.append("weighted_target_price_not_reproducible")
    return sorted(set(issues))


def _growth(previous: Any, current: Any) -> float | None:
    if not isinstance(previous, (int, float)) or not isinstance(current, (int, float)) or previous == 0:
        return None
    return current / previous - 1


def _delta(previous: Any, current: Any) -> float | None:
    if not isinstance(previous, (int, float)) or not isinstance(current, (int, float)):
        return None
    return float(current) - float(previous)


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)
