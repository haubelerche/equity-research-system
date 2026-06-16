from __future__ import annotations

from backend.reporting.spec_builder import build_report_specs


def test_specs_map_each_chart_and_table_to_source_artifacts() -> None:
    specs = build_report_specs(
        {
            "required_charts": ["revenue_by_channel", "forecast_revenue"],
            "required_tables": ["valuation_summary"],
        },
        {
            "company_research_pack": {"ticker": "DHG"},
            "forecast_model": {"ticker": "DHG"},
            "valuation": {"ticker": "DHG"},
        },
    )

    charts = specs["chart_specs"]["charts"]
    tables = specs["table_specs"]["tables"]
    assert charts[0]["source_artifact_refs"] == ["company_research_pack", "forecast_model"]
    assert charts[1]["source_artifact_refs"] == ["forecast_model"]
    assert tables[0]["source_artifact_refs"] == ["valuation"]


def test_price_chart_resolves_market_source_without_a_build_time_artifact() -> None:
    # stock_price_vs_benchmark is rendered from market data fetched at publish time,
    # so its source must resolve even though no market_snapshot/market_data artifact
    # exists in the WRITE_REPORT artifacts dict. Otherwise the professional-presentation
    # gate flags chart_metadata_incomplete + chart_source_map_missing for it.
    specs = build_report_specs(
        {"required_charts": ["stock_price_vs_benchmark"], "required_tables": []},
        {},  # no artifacts present at build time
    )
    chart = specs["chart_specs"]["charts"][0]
    assert chart["source"], "price chart must have a non-empty source"
    assert chart["source_artifact_refs"], "price chart must have source_artifact_refs"
    assert any(chart["source_map"].values()), "price chart source_map must be non-empty"
