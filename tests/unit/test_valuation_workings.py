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
                "gross_profit": 2000,
                "ebit": 1200,
                "net_income": 900,
                "capex": -200,
                "depreciation": 150,
                "eps": 6000,
            },
            {"label": "2027F", "revenue": 5500, "ebit": 1300, "net_income": 980, "eps": 6500},
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
    ]:
        assert english_term not in md
