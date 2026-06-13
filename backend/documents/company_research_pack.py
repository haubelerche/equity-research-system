"""Build a company-specific research pack without fabricating missing evidence."""
from __future__ import annotations

from typing import Any

from backend.news.analyst_insight import build_analyst_insights


_COMMON_TOPICS = (
    "company_profile",
    "business_segments",
    "market_share",
    "peer_positioning",
    "catalysts",
    "risks",
)

_ARCHETYPE_TOPICS = {
    "branded_generic_manufacturer": (
        "revenue_by_channel",
        "revenue_by_product_group",
        "capacity_and_factory_status",
        "regulatory_and_gmp_status",
        "api_exposure",
        "distribution_network",
    ),
    "tender_focused_manufacturer": (
        "revenue_by_channel",
        "revenue_by_product_group",
        "tender_metrics",
        "capacity_and_factory_status",
        "regulatory_and_gmp_status",
        "api_exposure",
    ),
    "traditional_medicine": (
        "revenue_by_channel",
        "revenue_by_product_group",
        "capacity_and_factory_status",
        "distribution_network",
    ),
    "distributor": (
        "revenue_by_channel",
        "distribution_network",
    ),
    "medical_equipment": (
        "revenue_by_product_group",
        "tender_metrics",
        "distribution_network",
    ),
    "healthcare_services": (
        "revenue_by_channel",
        "capacity_and_factory_status",
    ),
}


def _first_mapping(*values: Any) -> dict[str, Any]:
    for value in values:
        if isinstance(value, dict) and value:
            return value
    return {}


def _first_list(*values: Any) -> list[Any]:
    for value in values:
        if isinstance(value, list) and value:
            return value
    return []


def build_company_research_pack(
    *,
    ticker: str,
    evidence_pack: dict[str, Any] | None = None,
    financial_analysis: dict[str, Any] | None = None,
    archetype: str | None = None,
) -> dict[str, Any]:
    """Normalize available company evidence and explicitly expose coverage gaps."""
    evidence_pack = evidence_pack or {}
    financial_analysis = financial_analysis or {}
    business = evidence_pack.get("business_evidence") or {}
    catalysts = evidence_pack.get("pharma_catalyst_evidence") or {}
    segments = financial_analysis.get("segment_channel_analysis") or {}
    interpretation = financial_analysis.get("business_interpretation") or {}
    resolved_archetype = str(
        archetype
        or business.get("archetype")
        or interpretation.get("archetype")
        or "branded_generic_manufacturer"
    )
    if resolved_archetype not in _ARCHETYPE_TOPICS:
        resolved_archetype = "branded_generic_manufacturer"
    required_topics = tuple(dict.fromkeys(
        (*_COMMON_TOPICS, *_ARCHETYPE_TOPICS[resolved_archetype])
    ))

    pack: dict[str, Any] = {
        "schema_version": "1.0",
        "ticker": ticker.upper(),
        "archetype": resolved_archetype,
        "company_profile": _first_mapping(business.get("company_profile"), interpretation.get("company_profile")),
        "business_segments": _first_mapping(business.get("business_segments"), segments.get("business_segments")),
        "revenue_by_channel": _first_mapping(business.get("revenue_by_channel"), segments.get("revenue_by_channel")),
        "revenue_by_product_group": _first_mapping(
            business.get("revenue_by_product_group"),
            segments.get("revenue_by_product_group"),
        ),
        "tender_metrics": _first_mapping(business.get("tender_metrics"), segments.get("tender_metrics")),
        "market_share": _first_mapping(business.get("market_share"), segments.get("market_share")),
        "capacity_and_factory_status": _first_mapping(business.get("capacity_and_factory_status")),
        "regulatory_and_gmp_status": _first_mapping(
            business.get("regulatory_and_gmp_status"),
            catalysts.get("regulatory_and_gmp_status"),
        ),
        "api_exposure": _first_mapping(business.get("api_exposure"), catalysts.get("api_exposure")),
        "distribution_network": _first_mapping(business.get("distribution_network")),
        "peer_positioning": _first_mapping(business.get("peer_positioning"), interpretation.get("peer_positioning")),
        "catalysts": _first_list(business.get("catalysts"), catalysts.get("catalysts")),
        "risks": _first_list(business.get("risks"), financial_analysis.get("financial_risks")),
        "source_map": _first_mapping(evidence_pack.get("source_map")),
    }
    catalyst_events = (
        catalysts.get("events")
        or catalysts.get("catalysts")
        or [item for item in pack["catalysts"] if isinstance(item, dict)]
    )
    pack["analyst_insights"] = build_analyst_insights(
        catalyst_events if isinstance(catalyst_events, list) else []
    )
    missing = [topic for topic in required_topics if not pack.get(topic)]
    pack["coverage"] = {
        "required_topics": len(required_topics),
        "required_topic_names": list(required_topics),
        "covered_topics": len(required_topics) - len(missing),
        "coverage_ratio": (len(required_topics) - len(missing)) / len(required_topics),
        "missing_topics": missing,
    }
    pack["limitations"] = [
        f"missing_company_specific_evidence:{topic}" for topic in missing
    ]
    return pack
