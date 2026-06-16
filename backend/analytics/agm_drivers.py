"""Map the AGM (ĐHCĐ) driver pack onto ForecastAssumptions kwargs.

The shareholder-approved 2026 plan is a PRIORITY forecast driver: the first forecast
year uses the company's own stated revenue-growth target and disclosed borrowing plan
instead of historical medians. Every override carries source/page provenance in
``driver_sources`` — and we deliberately do NOT set ``assumption_status`` or
``debt_schedule_approved`` (the debt-schedule auto-approve bug laundered a median into a
fake analyst override; AGM provenance is honest, not an approval claim).
"""
from __future__ import annotations

from typing import Any


def build_agm_assumptions(
    agm_pack: dict[str, Any], *, latest_revenue: float | None = None
) -> dict[str, Any]:
    """Return ForecastAssumptions kwargs derived from an agm_pack.

    Always returns a ``driver_sources`` dict (possibly empty); other keys are present
    only when the AGM actually disclosed them. When the plan gives an absolute 2026
    revenue target but no explicit growth %, ``latest_revenue`` (the most recent actual)
    lets us derive the implied growth."""
    agm_pack = agm_pack if isinstance(agm_pack, dict) else {}
    out: dict[str, Any] = {}
    sources: dict[str, Any] = {}

    targets = agm_pack.get("targets_2026") if isinstance(agm_pack.get("targets_2026"), dict) else {}
    growth_pct = targets.get("revenue_growth_pct")
    revenue_target = targets.get("revenue")
    growth: float | None = None
    if isinstance(growth_pct, (int, float)):
        growth = round(float(growth_pct) / 100.0, 6)
    elif isinstance(revenue_target, (int, float)) and isinstance(latest_revenue, (int, float)) and latest_revenue:
        growth = round(float(revenue_target) / float(latest_revenue) - 1.0, 6)
    if growth is not None:
        out["revenue_growth_override"] = growth
        sources["revenue_growth_override"] = {
            "source": "agm_2026", "page": targets.get("page"), "value": growth,
        }

    plan_rows = [
        {"year": r.get("year"), "amount": r.get("amount"),
         "description": r.get("description", ""), "page": r.get("page")}
        for r in (agm_pack.get("borrowing_plan") or [])
        if isinstance(r, dict) and r.get("year") is not None and r.get("amount") is not None
    ]
    if plan_rows:
        out["pdf_debt_plan"] = plan_rows
        sources["pdf_debt_plan"] = {
            "source": "agm_2026", "pages": [r["page"] for r in plan_rows if r["page"]],
        }

    out["driver_sources"] = sources
    return out
