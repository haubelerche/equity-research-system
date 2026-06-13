from __future__ import annotations

from backend.news.analyst_insight import build_analyst_insight


def test_event_to_insight_is_ready_only_with_financial_transmission() -> None:
    insight = build_analyst_insight({
        "event_title": "DHG factory receives approval",
        "ticker": "DHG",
        "source_document_id": 10,
        "materiality": "high",
        "financial_transmission": {
            "affected_drivers": ["capacity_utilization"],
            "affected_line_items": ["revenue", "gross_margin"],
            "direction": "positive",
            "time_horizon": "2027-2028",
            "magnitude_range": "revenue +3% to +5%",
        },
        "thesis_implication": "Supports the capacity-led growth thesis.",
        "falsification_trigger": "Commercial production misses 2027.",
        "confidence": "medium",
    })

    assert insight["status"] == "ready"
    assert insight["evidence_refs"] == ["source_document:10"]


def test_event_to_insight_exposes_missing_transmission_without_fabrication() -> None:
    insight = build_analyst_insight({
        "event_title": "Industry policy changed",
        "materiality": "unknown",
    })

    assert insight["status"] == "insufficient_evidence"
    assert "financial_transmission.affected_drivers" in insight["missing_fields"]
    assert insight["valuation_delta"] is None
