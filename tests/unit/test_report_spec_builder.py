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
