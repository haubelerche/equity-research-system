from __future__ import annotations

from backend.news.analyst_insight import build_analyst_insight


def test_event_to_insight_is_ready_only_with_financial_transmission() -> None:
    insight = build_analyst_insight({
        "event_title": "DHG factory receives approval",
        "ticker": "DHG",
        "source_document_id": 10,
        "materiality": "high",
        "operating_cause": "Regulatory approval enables commercial production.",
        "financial_transmission": {
            "affected_drivers": ["capacity_utilization"],
            "affected_line_items": ["revenue", "gross_margin"],
            "direction": "positive",
            "time_horizon": "2027-2028",
            "magnitude_range": "revenue +3% to +5%",
        },
        "scenario_delta": {"revenue_growth_pct": 3},
        "valuation_delta": {"target_price_pct": 2},
        "monitoring_kpi": "Commercial production start date",
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


def test_event_to_insight_computes_numeric_deltas_from_explicit_sensitivity() -> None:
    insight = build_analyst_insight({
        "event_title": "Tender award",
        "ticker": "DHG",
        "source_document_id": 11,
        "materiality": "high",
        "operating_cause": "Award increases committed hospital volume.",
        "revenue_impact_pct": 5,
        "margin_impact_bps": 100,
        "target_price_impact_pct": 2,
        "financial_base": {"revenue": 1000, "ebit": 200, "target_price_vnd": 100000},
        "financial_transmission": {
            "affected_drivers": ["ETC volume"],
            "affected_line_items": ["revenue", "ebit"],
            "direction": "positive",
            "time_horizon": "2026",
        },
        "thesis_implication": "Supports ETC growth.",
        "falsification_trigger": "Award is cancelled.",
        "monitoring_kpi": "Tender delivery volume",
        "confidence": "high",
    })

    assert insight["scenario_delta"]["revenue_delta"] == 50
    assert insight["scenario_delta"]["ebit_delta"] == 10
    assert insight["valuation_delta"]["target_price_delta_vnd"] == 2000
