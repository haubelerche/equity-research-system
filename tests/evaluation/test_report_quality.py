from __future__ import annotations

from backend.evaluation.report_quality import (
    build_pharma_driver_model,
    build_valuation_bridge,
    citation_coverage_gate,
    evaluate_report_quality,
    financial_model_integrity_gate,
    forecast_reasonableness_gate,
    professional_presentation_gate,
    recommendation_consistency_gate,
    valuation_completeness_gate,
)
from backend.documents.company_research_pack import build_company_research_pack


def _forecast() -> dict:
    return {
        "forecast_years": [
            {
                "label": "2025A", "revenue": 5_267, "gross_margin": 0.476,
                "ebit_margin": 0.203, "net_income": 852, "eps": 6_308,
                "diluted_shares": 135.07, "total_assets": 6_000, "equity": 4_500,
                "total_debt": 200, "cash": 1_000, "other_liabilities": 1_300,
            },
            {
                "label": "2026F", "revenue": 5_480, "gross_margin": 0.472,
                "ebit_margin": 0.272, "net_income": 1_312, "eps": 10_033,
                "diluted_shares": 130.77, "total_assets": 6_500, "equity": 5_000,
                "total_debt": 200, "cash": 1_100, "other_liabilities": 1_300,
            },
        ],
        "drivers": {"revenue_growth": {"2026": 0.04}},
        "revenue_by_channel": {"ETC": {}, "OTC": {}},
        "revenue_by_product_group": {"core_pharma": {}},
    }


def _valuation() -> dict:
    return {
        "selected_methods": ["FCFF", "FCFE"],
        "current_price_vnd": 93_700,
        "fcff": {
            "wacc": 0.138,
            "wacc_breakdown": {"risk_free_rate": 0.04, "cost_of_equity": 0.14},
            "terminal_growth": 0.03,
            "fcff_table": [{"label": "2026F", "fcff": 900}],
            "terminal_value": 10_000,
            "pv_terminal_value": 6_000,
            "enterprise_value": 8_000,
            "net_debt": -800,
            "equity_value": 8_800,
            "shares_mn": 130.77,
            "target_price_vnd": 67_294,
            "net_debt_bridge": {
                "cash": 1_000, "short_term_investments": 0, "total_debt": 200,
            },
        },
        "fcfe": {
            "fcfe_table": [{"label": "2026F", "fcfe": 800}],
            "equity_value": 8_500,
        },
    }


def test_profit_growth_sanity_requires_bridge() -> None:
    result = forecast_reasonableness_gate({
        **_forecast(),
        "pharma_driver_model": build_pharma_driver_model(_forecast()),
    })
    assert not result["passed"]
    assert "profit_growth_requires_bridge:2026F" in result["blocking_reasons"]


def test_ebit_margin_jump_requires_operating_leverage_bridge() -> None:
    result = forecast_reasonableness_gate({
        **_forecast(),
        "pharma_driver_model": build_pharma_driver_model(_forecast()),
    })
    assert "ebit_margin_jump_without_gross_margin_support:2026F" in result["blocking_reasons"]


def test_fcfe_naming_integrity_blocks_missing_model() -> None:
    valuation = _valuation()
    valuation["fcfe"] = {}
    result = valuation_completeness_gate(valuation, {"text": "FCFF/FCFE"})
    assert not result["passed"]
    assert "report_mentions_missing_valuation_method:FCFE" in result["blocking_reasons"]


def test_dividend_consistency_blocks_zero_yield() -> None:
    forecast = _forecast()
    forecast["forecast_years"][1]["cash_dividend"] = 500
    forecast["forecast_years"][1]["dividend_yield"] = 0
    result = financial_model_integrity_gate(forecast, _valuation())
    assert "dividend_yield_total_return_inconsistent:2026F" in result["blocking_reasons"]


def test_balance_sheet_completeness_blocks_blank_liabilities() -> None:
    forecast = _forecast()
    forecast["forecast_years"][1]["other_liabilities"] = None
    result = financial_model_integrity_gate(forecast, _valuation())
    assert any(reason.startswith("balance_sheet_incomplete:2026F") for reason in result["blocking_reasons"])


def test_quantitative_citation_coverage_requires_lineage() -> None:
    report = {
        "claims": [
            {"claim_id": f"c{i}", "claim_type": "quantitative", "fact_id": f"f{i}" if i < 80 else None}
            for i in range(100)
        ]
    }
    result = citation_coverage_gate(report)
    assert not result["passed"]
    assert result["summary"]["coverage_ratio"] == 0.8
    assert result["blocking_reasons"] == ["citation_coverage_below_threshold:80/100"]


def test_production_quantitative_boolean_contract_requires_lineage() -> None:
    report = {
        "claims": [
            {
                "claim_id": "c1",
                "claim_type": "fact",
                "quantitative": True,
                "supporting_refs": [],
                "source_artifact_refs": [],
            },
            {
                "claim_id": "c2",
                "claim_type": "fact",
                "quantitative": False,
            },
        ]
    }

    result = citation_coverage_gate(report)

    assert not result["passed"]
    assert result["summary"]["quantitative_claims"] == 1
    assert result["blocking_reasons"] == ["citation_coverage_below_threshold:0/1"]


def test_recommendation_hidden_before_approval() -> None:
    result = recommendation_consistency_gate(
        {"recommendation": "HOLD", "target_price_vnd": 100_000},
        "under_review",
    )
    assert not result["passed"]
    assert result["blocking_reasons"] == ["recommendation_visible_before_approval"]


def test_builders_expose_driver_and_reproducible_valuation_contracts() -> None:
    driver = build_pharma_driver_model(_forecast())
    bridge = build_valuation_bridge(_valuation())
    assert set(driver["revenue"]["by_channel"]) == {"ETC", "OTC"}
    assert bridge["fcff_table"][0]["fcff"] == 900
    assert bridge["equity_bridge"]["target_price"] == 67_294
    assert bridge["terminal_value"]["terminal_value_share_of_ev"] == 0.75


def test_company_research_pack_exposes_missing_evidence_without_fabrication() -> None:
    pack = build_company_research_pack(
        ticker="DHG",
        evidence_pack={"business_evidence": {"revenue_by_channel": {"ETC": 1, "OTC": 2}}},
        financial_analysis={"financial_risks": ["API cost"]},
    )
    assert set(pack["revenue_by_channel"]) == {"ETC", "OTC"}
    assert pack["market_share"] == {}
    assert "market_share" in pack["coverage"]["missing_topics"]


def test_company_research_pack_uses_archetype_specific_requirements() -> None:
    pack = build_company_research_pack(
        ticker="TST",
        archetype="healthcare_services",
        evidence_pack={"business_evidence": {"company_profile": {"name": "Hospital"}}},
    )

    assert pack["archetype"] == "healthcare_services"
    assert "api_exposure" not in pack["coverage"]["required_topic_names"]
    assert "regulatory_and_gmp_status" not in pack["coverage"]["required_topic_names"]


def test_professional_presentation_requires_numbered_sourced_specs() -> None:
    result = professional_presentation_gate({
        "sections": {
            "cover_investment_summary": {"text": "x"},
            "recent_financial_performance": {"text": "x"},
            "driver_based_forecast": {"text": "x"},
            "valuation_and_recommendation": {"text": "x"},
            "risks_and_monitoring_factors": {"text": "x"},
            "appendix": {"text": "x"},
        },
        "chart_specs": {"charts": [{"id": "C1", "title": "Revenue"}]},
        "table_specs": {"tables": [{"id": "T1", "title": "Forecast", "source": "valuation"}]},
    })

    assert not result["passed"]
    assert "chart_metadata_incomplete:C1" in result["blocking_reasons"]


def test_report_quality_blocks_negative_dhg_sample_with_exact_reasons() -> None:
    forecast = _forecast()
    forecast["pharma_driver_model"] = build_pharma_driver_model(forecast)
    valuation = _valuation()
    valuation["fcfe"] = {}
    report = {
        "recommendation": "HOLD",
        "target_price_vnd": 106_752,
        "claims": [{"claim_id": "generic", "claim_type": "quantitative", "source": "Hệ thống"}],
        "text": "Mô hình FCFF/FCFE",
    }
    result = evaluate_report_quality(
        forecast=forecast,
        valuation=valuation,
        report=report,
        approval_status="under_review",
    )
    assert result["decision"] == "block_export"
    assert result["score"] < 70
    assert set(result["failed_gates"]) >= {
        "forecast_reasonableness",
        "valuation_completeness",
        "citation_coverage",
        "recommendation_consistency",
    }
