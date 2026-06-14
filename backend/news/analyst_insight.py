"""Deterministic event-to-insight artifacts with explicit evidence gaps."""
from __future__ import annotations

from typing import Any


def compute_causal_deltas(event: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Compute scenario and valuation deltas from explicit numeric sensitivities."""
    base = event.get("financial_base") or {}
    scenario: dict[str, Any] = {}
    revenue = base.get("revenue")
    revenue_impact = event.get("revenue_impact_pct")
    if isinstance(revenue, (int, float)) and isinstance(revenue_impact, (int, float)):
        scenario["revenue_delta"] = float(revenue) * float(revenue_impact) / 100
    ebit = base.get("ebit")
    margin_impact = event.get("margin_impact_bps")
    if isinstance(ebit, (int, float)) and isinstance(revenue, (int, float)) and isinstance(margin_impact, (int, float)):
        scenario["ebit_delta"] = float(revenue) * float(margin_impact) / 10_000
        scenario["ebit_after_delta"] = float(ebit) + scenario["ebit_delta"]
    target = base.get("target_price_vnd")
    target_impact = event.get("target_price_impact_pct")
    valuation = None
    if isinstance(target, (int, float)) and isinstance(target_impact, (int, float)):
        valuation = {
            "target_price_delta_vnd": float(target) * float(target_impact) / 100,
            "target_price_after_delta_vnd": float(target) * (1 + float(target_impact) / 100),
        }
    return scenario or None, valuation


def build_analyst_insight(event: dict[str, Any]) -> dict[str, Any]:
    """Normalize one researched event without inventing financial transmission."""
    observation = (
        event.get("observation")
        or event.get("claim")
        or event.get("event_title")
        or event.get("title")
    )
    evidence_refs = list(event.get("evidence_refs") or [])
    if event.get("source_document_id") is not None:
        evidence_refs.append(f"source_document:{event['source_document_id']}")
    evidence_refs = sorted(set(str(ref) for ref in evidence_refs if ref))

    financial_transmission = event.get("financial_transmission")
    if not isinstance(financial_transmission, dict):
        financial_transmission = {}

    computed_scenario, computed_valuation = compute_causal_deltas(event)
    insight = {
        "schema_version": "2.0",
        "observation": observation,
        "operating_cause": event.get("operating_cause"),
        "evidence_refs": evidence_refs,
        "company_specificity": event.get("company_specificity")
        or ("company_specific" if event.get("ticker") else "sector_level"),
        "novelty": event.get("novelty"),
        "materiality": event.get("materiality"),
        "financial_transmission": {
            "affected_drivers": financial_transmission.get("affected_drivers") or [],
            "affected_line_items": financial_transmission.get("affected_line_items") or [],
            "direction": financial_transmission.get("direction"),
            "time_horizon": financial_transmission.get("time_horizon"),
            "magnitude_range": financial_transmission.get("magnitude_range"),
        },
        "scenario_delta": event.get("scenario_delta") or computed_scenario,
        "valuation_delta": event.get("valuation_delta") or computed_valuation,
        "monitoring_kpi": event.get("monitoring_kpi"),
        "thesis_implication": event.get("thesis_implication"),
        "falsification_trigger": event.get("falsification_trigger"),
        "confidence": event.get("confidence"),
    }
    missing: list[str] = []
    for field in (
        "observation",
        "evidence_refs",
        "materiality",
        "operating_cause",
        "thesis_implication",
        "falsification_trigger",
        "scenario_delta",
        "valuation_delta",
        "monitoring_kpi",
        "confidence",
    ):
        if not insight.get(field):
            missing.append(field)
    for field in ("affected_drivers", "affected_line_items", "direction", "time_horizon"):
        if not insight["financial_transmission"].get(field):
            missing.append(f"financial_transmission.{field}")
    insight["status"] = "ready" if not missing else "insufficient_evidence"
    insight["missing_fields"] = missing
    return insight


def build_analyst_insights(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [build_analyst_insight(event) for event in events if isinstance(event, dict)]
