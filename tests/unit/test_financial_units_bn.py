"""Regression: monetary facts must render in tỷ đồng (bn), per-share/counts stay native."""
from __future__ import annotations

from backend.reporting.client_report_view_model import _fact_value


def _facts():
    return {
        "revenue.net": {"2025FY": 5_266_962_684_050.0},
        "net_income.parent": {"2025FY": 852_354_107_582.0},
        "total_assets.ending": {"2025FY": 5_173_881_628_997.0},
        "eps.basic": {"2025FY": 6308.0},
        "shares_outstanding.ending": {"2025FY": 130_746_071.0},
    }


def test_monetary_metrics_scaled_to_billions():
    facts = _facts()
    assert round(_fact_value(facts, "revenue.net", "2025FY")) == 5267
    assert round(_fact_value(facts, "net_income.parent", "2025FY")) == 852
    assert round(_fact_value(facts, "total_assets.ending", "2025FY")) == 5174


def test_per_share_and_counts_not_scaled():
    facts = _facts()
    # EPS is VND/share — must stay native, not divided to bn.
    assert _fact_value(facts, "eps.basic", "2025FY") == 6308.0
    # Share count must stay a count, not be scaled.
    assert _fact_value(facts, "shares_outstanding.ending", "2025FY") == 130_746_071.0


def test_nested_dict_fact_format_also_scaled():
    facts = {"revenue.net": {"2025FY": {"value": 5_266_962_684_050.0, "unit": "VND"}}}
    assert round(_fact_value(facts, "revenue.net", "2025FY")) == 5267


def test_missing_fact_returns_none():
    assert _fact_value({}, "revenue.net", "2025FY") is None
