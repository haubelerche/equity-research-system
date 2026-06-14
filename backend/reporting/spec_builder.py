"""Build auditable chart/table specifications from the report inventory."""
from __future__ import annotations

from typing import Any


_SOURCE_BY_TOKEN = {
    "price": ("market_snapshot", "market_data"),
    "trading": ("market_snapshot",),
    "channel": ("company_research_pack", "forecast_model"),
    "product": ("company_research_pack", "forecast_model"),
    "market_share": ("company_research_pack",),
    "financial": ("financial_analysis", "forecast_model"),
    "margin": ("financial_analysis", "forecast_model"),
    "forecast": ("forecast_model",),
    "valuation": ("valuation",),
    "dcf": ("valuation",),
    "fcff": ("valuation",),
    "fcfe": ("valuation",),
    "risk": ("analyst_insight_pack", "company_research_pack"),
}


def build_report_specs(report_draft: dict[str, Any], artifacts: dict[str, Any]) -> dict[str, Any]:
    """Return deterministic specs with explicit source-artifact ownership."""
    return {
        "chart_specs": {
            "charts": [
                _spec(item, "chart", artifacts)
                for item in report_draft.get("required_charts") or []
            ]
        },
        "table_specs": {
            "tables": [
                _spec(item, "table", artifacts)
                for item in report_draft.get("required_tables") or []
            ]
        },
    }


def _spec(item: Any, kind: str, artifacts: dict[str, Any]) -> dict[str, Any]:
    if isinstance(item, dict):
        identifier = str(item.get(f"{kind}_id") or item.get("id") or item.get("name") or "")
        status = item.get("status") or "present"
    else:
        identifier = str(item)
        status = "present"
    candidates: list[str] = []
    lowered = identifier.lower()
    for token, owners in _SOURCE_BY_TOKEN.items():
        if token in lowered:
            candidates.extend(owners)
    refs = [owner for owner in dict.fromkeys(candidates) if artifacts.get(owner)]
    return {
        f"{kind}_id": identifier,
        "id": identifier,
        "title": identifier.replace("_", " ").strip().title(),
        "status": status,
        "source": ", ".join(refs),
        "source_artifact_refs": refs,
        "source_map": {identifier: refs},
    }
