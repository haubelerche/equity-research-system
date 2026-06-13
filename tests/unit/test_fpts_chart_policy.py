from backend.reporting.fpts_chart_policy import (
    FPTS_ADDITIONAL_ALLOWED_FAMILIES,
    FPTS_CHART_POLICY,
    is_main_report_chart,
    main_report_chart_ids,
)


def test_only_fpts_aligned_registry_charts_enter_main_report() -> None:
    assert main_report_chart_ids([f"C{i}" for i in range(1, 9)]) == ["C1", "C2", "C4", "C5"]


def test_valuation_visualizations_are_table_only() -> None:
    assert FPTS_CHART_POLICY["C6"].disposition == "table_only"
    assert FPTS_CHART_POLICY["C7"].disposition == "table_only"
    assert FPTS_CHART_POLICY["C8"].disposition == "table_only"
    assert not is_main_report_chart("C7")


def test_reference_chart_families_cover_market_share_and_recommendation_history() -> None:
    assert "market_share_period_comparison_donut" in FPTS_ADDITIONAL_ALLOWED_FAMILIES
    assert "recommendation_history" in FPTS_ADDITIONAL_ALLOWED_FAMILIES
