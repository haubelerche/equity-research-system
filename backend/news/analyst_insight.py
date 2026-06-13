"""Deterministic event-to-insight artifacts with explicit evidence gaps."""
from __future__ import annotations

from typing import Any


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

    insight = {
        "schema_version": "1.0",
        "observation": observation,
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
        "scenario_delta": event.get("scenario_delta"),
        "valuation_delta": event.get("valuation_delta"),
        "thesis_implication": event.get("thesis_implication"),
        "falsification_trigger": event.get("falsification_trigger"),
        "confidence": event.get("confidence"),
    }
    missing: list[str] = []
    for field in (
        "observation",
        "evidence_refs",
        "materiality",
        "thesis_implication",
        "falsification_trigger",
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
