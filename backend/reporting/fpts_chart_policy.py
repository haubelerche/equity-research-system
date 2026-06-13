"""FPTS-aligned chart policy for client-facing equity research reports."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ChartDisposition = Literal["main_report", "appendix_only", "table_only"]


@dataclass(frozen=True)
class ChartPolicy:
    chart_id: str
    family: str
    disposition: ChartDisposition
    preferred_width: Literal["sidebar", "half", "full"]
    rationale: str


FPTS_CHART_POLICY: dict[str, ChartPolicy] = {
    "C1": ChartPolicy(
        "C1",
        "stock_price_vs_benchmark",
        "main_report",
        "sidebar",
        "FPTS places the indexed stock-price comparison in the cover-page sidebar.",
    ),
    "C2": ChartPolicy(
        "C2",
        "historical_revenue_and_growth",
        "main_report",
        "full",
        "FPTS uses clustered bars with one or two growth or margin lines.",
    ),
    "C3": ChartPolicy(
        "C3",
        "eps_and_pe_history",
        "appendix_only",
        "half",
        "The reference report presents valuation multiples in tables, not as a main-report chart.",
    ),
    "C4": ChartPolicy(
        "C4",
        "margin_trend",
        "main_report",
        "full",
        "Margin trends are permitted when directly tied to the adjacent operating thesis.",
    ),
    "C5": ChartPolicy(
        "C5",
        "forecast_revenue_and_profit",
        "main_report",
        "half",
        "FPTS repeatedly pairs forecast bars and growth lines with driver-specific narrative.",
    ),
    "C6": ChartPolicy(
        "C6",
        "dcf_waterfall",
        "table_only",
        "full",
        "The reference valuation chapter uses result, assumption, and bridge tables instead of a waterfall.",
    ),
    "C7": ChartPolicy(
        "C7",
        "valuation_sensitivity_heatmap",
        "table_only",
        "full",
        "Sensitivity is a matrix table in an FPTS-aligned report, not a heatmap chart.",
    ),
    "C8": ChartPolicy(
        "C8",
        "peer_multiple_comparison",
        "table_only",
        "full",
        "Peer valuation belongs in a compact comparison table unless a reference-template exception exists.",
    ),
}


FPTS_ADDITIONAL_ALLOWED_FAMILIES = frozenset(
    {
        "revenue_by_channel",
        "product_group_revenue",
        "market_share_pie",
        "market_share_period_comparison_donut",
        "tender_value_and_volume",
        "forecast_revenue_by_driver",
        "recommendation_history",
        "composition_pie_appendix",
    }
)


def is_main_report_chart(chart_id: str) -> bool:
    policy = FPTS_CHART_POLICY.get(chart_id)
    return bool(policy and policy.disposition == "main_report")


def main_report_chart_ids(chart_ids: list[str]) -> list[str]:
    return [chart_id for chart_id in chart_ids if is_main_report_chart(chart_id)]

