"""Tests for the valuation workings (.md) explainer builder.

The builder is a pure function: it takes already-loaded artifact dicts and a view
model, and returns a deterministic Markdown string that explains every valuation
calculation for internal verification. No I/O, no fabrication.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.reporting.valuation_workings import (
    SECTION_TITLES,
    build_report_explanation_md,
    build_valuation_workings_md,
)


def _sample_valuation() -> dict:
    return {
        "current_price": 75000,
        "target_price": 101546,
        "upside_downside": 0.354,
        "reproducibility_hash": "abc123",
        "valuation_date": "2026-06-12",
        "snapshot_id": "snap-DHG-001",
        "base_year": 2025,
        "fcff_dcf": {
            "wacc": 0.138,
            "terminal_growth": 0.03,
            "pv_fcff": 4416.9,
            "terminal_value": 13355.0,
            "pv_terminal_value": 6997.3,
            "enterprise_value": 11414.2,
            "net_debt": -129.9,
            "equity_value": 11544.1,
            "shares_outstanding": 130.7,
            "implied_price": 88294.0,
            "terminal_value_weight": 0.613,
            "fcff_table": [
                {
                    "label": "2026F",
                    "ebit": 1200,
                    "tax_rate": 0.2,
                    "depreciation": 150,
                    "capex": -200,
                    "delta_nwc": -50,
                    "fcff": 900,
                    "discount_factor": 0.879,
                    "pv": 791,
                },
                {"label": "2027F", "fcff": 980, "pv": 763},
            ],
        },
        "fcfe_dcf": {
            "cost_of_equity": 0.138,
            "terminal_growth": 0.03,
            "equity_value": 9030.0,
            "implied_price": None,
        },
        "blend": {
            "price_fcff_vnd": 88294,
            "price_fcfe_vnd": None,
            "fcff_weight": 0.6,
            "fcfe_weight": 0.4,
            "target_price_dcf_vnd": 101546,
            "current_price_vnd": 75000,
            "upside_pct": 0.354,
            "fcff_fcfe_gap_pct": None,
            "is_draft_only": False,
            "warnings": [],
            "formula": "Target Price = 0.60 × Price_FCFF + 0.40 × Price_FCFE",
        },
        "sensitivity": {
            "blend_grid": {
                "price_fcff_range": [80000, 88294, 95000],
                "price_fcfe_range": [8000, 9030, 10000],
                "matrix": [
                    [51200, 54518, 57200],
                    [54518, 57838, 60519],
                    [57200, 60519, 63200],
                ],
                "unit": "VND",
                "formula": "0.6×FCFF + 0.4×FCFE",
                "label": "Blend",
            },
            "fcff_wacc_g": {
                "wacc_range": [0.13, 0.138, 0.15],
                "g_range": [0.02, 0.03, 0.04],
                "matrix": [[1, 2, 3], [4, 5, 6], [7, 8, 9]],
                "unit": "VND",
                "base_wacc": 0.138,
            },
            "pe": {
                "eps_range": [5000, 6000, 7000],
                "pe_range": [12, 15, 18],
                "matrix": [[1, 2, 3], [4, 5, 6], [7, 8, 9]],
                "unit": "VND",
                "pe_label": "P/E",
            },
        },
        "assumptions": {
            "wacc": 0.1,
            "terminal_growth": 0.03,
            "forecast_years": 5,
            "target_pe": 15.0,
            "note": "Assumptions are defaults — must be reviewed and approved.",
        },
    }


def _sample_forecast() -> dict:
    return {
        "forecast_years": [
            {
                "label": "2026F",
                "revenue": 5000,
                "cogs": -3000,
                "gross_profit": 2000,
                "sga": -800,
                "ebit": 1200,
                "interest_expense": -100,
                "profit_before_tax": 1100,
                "tax_expense": -200,
                "net_income": 900,
                "capex": -200,
                "depreciation": 150,
                "eps": 6000,
            },
            {
                "label": "2027F",
                "revenue": 5500,
                "cogs": -3300,
                "gross_profit": 2200,
                "sga": -900,
                "ebit": 1300,
                "interest_expense": -120,
                "profit_before_tax": 1180,
                "tax_expense": -200,
                "net_income": 980,
                "capex": -220,
                "depreciation": 160,
                "eps": 6500,
            },
        ],
        "debt_schedule": {
            "forecast_rows": [
                {"label": "2026F", "net_borrowing": -100, "ending_interest_bearing_debt": 500}
            ]
        },
        "dividend_schedule": {
            "forecast_rows": [{"label": "2026F", "cash_dividend": 300, "payout_ratio": 0.33}]
        },
    }


def _sample_facts() -> dict:
    return {"revenue.net": {"2025FY": 4_500_000_000_000}}


def _sample_view_model() -> SimpleNamespace:
    return SimpleNamespace(
        ticker="DHG",
        company_name="CTCP Dược Hậu Giang",
        exchange="HOSE",
        sector="Dược phẩm",
        report_date="2026-06-12",
        publication_status="needs_human_review",
        missing_required_fields=["debt_schedule_publishable"],
        display_blocking_reasons=["blend_is_draft_only"],
        critic_findings=["fcff_fcfe_gap_gt_25pct"],
        recommendation="MUA",
        current_price=SimpleNamespace(amount=75000, currency="VND"),
        target_price=SimpleNamespace(amount=101546, currency="VND"),
        upside_downside=SimpleNamespace(value=0.354),
        valuation_evidence={
            "formula_trace_count": 5,
            "formula_trace_methods": ["fcff", "fcfe", "blend_dcf"],
            "peer_data_source": "VN pharma peers: IMP, DMC, TRA",
            "relative_valuation_status": "peer_data_available",
            "market_sanity_bridge": {"target_to_market": 1.354, "bridge_present": True},
            "display_blocking_reasons": ["blend_is_draft_only"],
            "policy_blocking_reasons": ["market_sanity_bridge_missing"],
            "model_warnings": ["FCFE BLOCKED - debt schedule unavailable"],
            "market_data_warnings": ["served from cache; live fetch failed"],
            "policy_warnings": ["valuation_method_divergence_warning"],
        },
    )


def _build(**overrides) -> str:
    kwargs = dict(
        ticker="DHG",
        run_id="run_dhg_001",
        valuation=_sample_valuation(),
        forecast=_sample_forecast(),
        facts=_sample_facts(),
        view_model=_sample_view_model(),
    )
    kwargs.update(overrides)
    return build_valuation_workings_md(**kwargs)


def _build_explanation(**overrides) -> str:
    kwargs = dict(
        ticker="DHG",
        run_id="run_dhg_001",
        valuation=_sample_valuation(),
        forecast=_sample_forecast(),
        facts=_sample_facts(),
        view_model=_sample_view_model(),
    )
    kwargs.update(overrides)
    return build_report_explanation_md(**kwargs)


def test_renders_all_eleven_section_titles():
    md = _build()
    assert len(SECTION_TITLES) == 11
    for title in SECTION_TITLES:
        assert f"## {title}" in md, f"missing section: {title}"


def test_renders_fcff_formula_and_wacc():
    md = _build()
    assert "FCFF = EBIT×(1−t) + D&A − CAPEX − ΔNWC" in md
    # WACC 0.138 must surface as a percentage somewhere in the FCFF section.
    assert "13.8%" in md


def test_renders_blend_arithmetic():
    md = _build()
    # 0.60 × 88,294 weighting must be shown explicitly.
    assert "0.60" in md and "0.40" in md
    assert "88,294" in md


def test_renders_sensitivity_matrix_as_markdown_table():
    md = _build()
    # blend_grid axis values and a table separator row must appear.
    assert "| ---" in md or "|---" in md
    assert "54,518" in md  # a matrix cell from blend_grid


def test_forecast_section_renders_full_income_statement_waterfall():
    md = _build()

    assert "| Doanh thu thuần | 5,000 | 5,500 |" in md
    assert "| Giá vốn hàng bán (COGS) | -3,000 | -3,300 |" in md
    assert "| Lợi nhuận gộp | 2,000 | 2,200 |" in md
    assert "| Chi phí SG&A | -800 | -900 |" in md
    assert "| EBIT | 1,200 | 1,300 |" in md
    assert "| Chi phí lãi vay | -100 | -120 |" in md
    assert "| Lợi nhuận trước thuế | 1,100 | 1,180 |" in md
    assert "| Chi phí thuế | -200 | -200 |" in md
    assert "| LNST cổ đông mẹ | 900 | 980 |" in md
    assert "| Khấu hao (D&A) | 150 | 160 |" in md
    assert "| CAPEX | -200 | -220 |" in md
    assert "| EPS (VND) | 6,000 | 6,500 |" in md


def test_forecast_section_explains_positive_gross_profit_with_negative_ebit():
    forecast = _sample_forecast()
    forecast["forecast_years"][0]["gross_profit"] = 100
    forecast["forecast_years"][0]["sga"] = -150
    forecast["forecast_years"][0]["ebit"] = -50

    md = _build(forecast=forecast)

    assert "Vì sao EBIT âm" in md
    assert "SG&A" in md
    assert "2026F" in md


def test_fcff_pv_computed_from_discount_factor_when_missing():
    val = _sample_valuation()
    val["fcff_dcf"]["pv_fcff"] = None
    val["fcff_dcf"]["fcff_table"][0].pop("pv")
    val["fcff_dcf"]["fcff_table"][0]["fcff"] = 900
    val["fcff_dcf"]["fcff_table"][0]["discount_factor"] = 0.879

    md = _build(valuation=val)

    assert "| PV(FCFF) | 791 | 763 |" in md
    assert "| PV dòng tiền dự phóng (Σ PV FCFF) | 1,554 |" in md


def test_fcff_explains_blank_price_when_equity_value_negative():
    val = _sample_valuation()
    val["fcff_dcf"]["equity_value"] = -211
    val["fcff_dcf"]["implied_price"] = None

    md = _build(valuation=val)

    assert "giá trị vốn chủ sở hữu âm" in md.lower()
    assert "không phải thiếu dữ liệu" in md.lower()


def test_fcfe_blank_price_reason_matches_negative_equity():
    val = _sample_valuation()
    val["fcfe_dcf"]["equity_value"] = -305
    val["fcfe_dcf"]["implied_price"] = None

    md = _build(valuation=val)

    assert "giá trị vốn chủ sở hữu âm" in md.lower()
    assert "thiếu dữ liệu vay ròng hoặc số cổ phiếu" not in md


def test_blend_explains_missing_when_component_price_absent():
    val = _sample_valuation()
    val["blend"]["price_fcff_vnd"] = None
    val["blend"]["price_fcfe_vnd"] = None
    val["blend"]["target_price_dcf_vnd"] = None

    md = _build(valuation=val)

    assert "0.60 × — + 0.40 × —" not in md
    assert "Chưa thể kết hợp" in md


def test_blend_still_shows_arithmetic_when_components_present():
    val = _sample_valuation()
    val["blend"]["price_fcfe_vnd"] = 9030
    val["blend"]["target_price_dcf_vnd"] = 56588

    md = _build(valuation=val)

    assert "`0.60 × 88,294 + 0.40 × 9,030 = 56,588`" in md


def test_decision_basis_explains_blank_target_chain():
    val = _sample_valuation()
    val["target_price"] = None
    val["upside_downside"] = None
    val["fcff_dcf"]["equity_value"] = -211
    val["fcff_dcf"]["implied_price"] = None
    val["fcfe_dcf"]["equity_value"] = -305
    val["fcfe_dcf"]["implied_price"] = None
    val["blend"]["price_fcff_vnd"] = None
    val["blend"]["price_fcfe_vnd"] = None
    val["blend"]["target_price_dcf_vnd"] = None
    val["blend"]["upside_pct"] = None
    forecast = _sample_forecast()
    forecast["forecast_years"][0]["gross_profit"] = 34
    forecast["forecast_years"][0]["sga"] = -84
    forecast["forecast_years"][0]["ebit"] = -50
    vm = _sample_view_model()
    vm.target_price = None
    vm.upside_downside = None
    vm.recommendation = "Giữ"

    md = _build_explanation(valuation=val, forecast=forecast, view_model=vm)

    assert "Vì sao giá mục tiêu để trống và khuyến nghị như vậy" in md
    assert "EBIT âm" in md
    assert "giá trị vốn chủ sở hữu âm" in md.lower()
    assert "không tính được mức tăng/giảm" in md.lower()


def test_translates_equity_value_and_cashsweep_warnings():
    val = _sample_valuation()
    val["blend"]["warnings"] = [
        "FCFF: equity value is negative — target price not computed",
        "FCFE: equity value is non-positive — target price not computed",
        "[CashSweep] 2026F: dividends_paid is negative (-20.66) — expected positive outflow; taking abs().",
        "[CashSweep] 2027F: dividends_paid is negative (-20.84) — expected positive outflow; taking abs().",
        "[CashSweep] 2028F: dividends_paid is negative (-21.02) — expected positive outflow; taking abs().",
    ]

    md = _build(valuation=val)

    assert "equity value is negative" not in md
    assert "dividends_paid" not in md
    assert "taking abs" not in md
    assert "[CashSweep]" not in md
    assert "giá trị vốn chủ sở hữu âm" in md.lower()
    assert md.count("Cổ tức dự phóng mang dấu âm") == 1


def test_translates_sga_and_cross_check_warning_leaks():
    vm = _sample_view_model()
    vm.valuation_evidence["model_warnings"] = [
        "SG&A not reported — derived from historical EBIT margin (3.0%) so forecast EBIT stays anchored to actuals.",
        "valuation_cross_check_divergence_warning",
    ]

    md = _build_explanation(view_model=vm)

    assert "SG&A not reported" not in md
    assert "valuation_cross_check_divergence" not in md
    assert "Chi phí bán hàng và quản lý chưa được công bố riêng" in md
    assert "Cảnh báo đối chiếu định giá" in md


def test_translates_english_critic_findings():
    vm = _sample_view_model()
    vm.critic_findings = [
        "[Major] The multiples module is intentionally marked pending and implied prices "
        "are blank because peer_pe_median and peer_ev_ebitda_median are not supplied.",
        "[cảnh báo] Simplified DCF and FCFF/FCFE runs include warnings about negative "
        "historical FCF in 2022 and terminal-value share-of-EV above recommended thresholds.",
    ]

    md = _build_explanation(view_model=vm)

    assert "peer_pe_median" not in md
    assert "terminal-value share-of-EV" not in md
    assert "[Major]" not in md
    assert "multiples" not in md.lower()


def test_explanation_evidence_block_not_duplicated():
    md = _build_explanation()

    assert md.count("## Minh chứng kiểm định") == 1


def test_standalone_workings_still_includes_crosscheck_evidence():
    md = _build()

    assert "Minh chứng kiểm định và phát hành" in md


def test_missing_values_render_as_dash_not_fabricated():
    val = _sample_valuation()
    val["fcfe_dcf"]["implied_price"] = None
    md = _build(valuation=val)
    # FCFE implied price is None -> must show the em dash, never a fabricated number.
    assert "—" in md


def test_defensive_key_naming_accepts_non_dcf_suffix():
    """Artifact may carry ``fcff``/``fcfe``/``blend`` instead of ``*_dcf``."""
    val = _sample_valuation()
    val["fcff"] = val.pop("fcff_dcf")
    val["fcfe"] = val.pop("fcfe_dcf")
    md = _build(valuation=val)
    assert "13.8%" in md  # WACC still resolved from fcff (no _dcf suffix)


def test_does_not_raise_on_empty_artifacts():
    md = build_valuation_workings_md(
        ticker="DHG",
        run_id="run_dhg_001",
        valuation={},
        forecast={},
        facts={},
        view_model=None,
    )
    assert "DHG" in md
    # Header section still rendered even with no data.
    assert f"## {SECTION_TITLES[0]}" in md


def test_report_explanation_embeds_full_valuation_workings():
    md = _build_explanation()

    assert "# Phụ lục giải trình định giá - DHG" in md
    assert "## Vì sao báo cáo chính kết luận như vậy" in md
    assert "## Chi tiết tính toán định giá" in md
    for title in SECTION_TITLES:
        assert f"## {title}" in md, f"missing section: {title}"

    assert "FCFF = EBIT×(1−t) + D&A − CAPEX − ΔNWC" in md
    assert "13.8%" in md
    assert "Giá trị cuối kỳ" in md
    assert "PV d" in md
    assert "0.60" in md and "0.40" in md
    assert "54,518" in md
    assert "P/E" in md
    assert "Mã băm tái lập" in md
    assert "abc123" in md


def test_report_explanation_surfaces_data_and_method_warnings():
    md = _build_explanation()

    assert "Lịch nợ vay chưa đủ" in md
    assert "Hai phương pháp dòng tiền" in md
    assert "Giá trị theo FCFF và FCFE lệch trên 25%" in md
    assert "Số vết công thức" in md
    assert "VN pharma peers: IMP, DMC, TRA" in md
    assert "served from cache; live fetch failed" in md


def test_report_explanation_translates_policy_blockers_and_mapping_warnings():
    view_model = _sample_view_model()
    view_model.valuation_evidence["policy_blocking_reasons"] = [
        "no_eligible_valuation_method",
        "valuation_method_divergence_critical",
        "valuation_result_not_publishable",
    ]
    view_model.valuation_evidence["model_warnings"] = [
        "target_pe=15.0x is model default — validate with peer-median P/E before publishing",
        "Relative valuation is PENDING — no peer_data_source provided. Target P/E, P/B, and EV/EBITDA require a real peer group dataset.",
        "EPS and target P/E are present but P/E implied price is blank",
        "fcfe_low_confidence",
    ]

    md = _build_explanation(view_model=view_model)

    assert "no_eligible_valuation_method" not in md
    assert "valuation_method_divergence_critical" not in md
    assert "target_pe=15.0x is model default" not in md
    assert "Relative valuation is PENDING" not in md
    assert "EPS and target P/E are present" not in md
    assert "Thiếu phương pháp định giá chính đã được xác minh" in md
    assert "Các phương pháp định giá cho kết quả phân kỳ mạnh" in md
    assert "Định giá tương đối thiếu bộ doanh nghiệp so sánh" in md
    assert "EPS dự phóng và P/E mục tiêu đã có" in md
    assert "P/E mục tiêu đang là giả định mặc định" in md
    assert "Lý do chặn công bố" not in md
    assert "recommendation_gate_not_allowed" not in md
    assert "valuation_result_not_publishable" not in md
    assert "peer_data_source" not in md
    assert "PENDING" not in md
    assert "BLOCKED" not in md
    assert "bị chặn" not in md


def test_report_explanation_translates_user_facing_finance_terms():
    md = _build_explanation()

    for english_term in [
        "Terminal value",
        "Enterprise value",
        "Equity value",
        "Cost of equity",
        "Premium/Discount",
        "driver-based",
        "sensitivity",
        "reproducibility_hash",
        "Lineage:",
        "canonical facts",
        "artifact định giá",
        "Lý do chặn công bố",
        "recommendation_gate_not_allowed",
        "valuation_result_not_publishable",
        "peer_data_source",
    ]:
        assert english_term not in md
