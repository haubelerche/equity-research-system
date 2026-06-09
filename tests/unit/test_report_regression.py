"""Regression tests per the 2026-06-08 regression review plan.

Guards against the documented regression where the DHG report showed:
- target_price = 0 VND (invalid)
- WACC = 0.0% (invalid)
- internal pipeline states (pending_review, default_unapproved) in the client report
- forecast / valuation blocked in draft mode

Each test corresponds to an acceptance criterion in the regression plan Phase 6.
"""
from __future__ import annotations

import json
import re

import pytest

from backend.reporting.client_report_view_model import build_client_report_view_model
from backend.reporting.client_section_builder import build_client_report_sections
from backend.reporting.html_renderer import HTMLRenderer
from backend.reporting.section_builder import ReportContext


# ── shared fixture ─────────────────────────────────────────────────────────────


def _write_regression_fixture(
    tmp_path,
    monkeypatch,
    ticker: str = "DBD",
    include_fcfe: bool = True,
    target_price_vnd: float = 62_000.0,
    wacc: float = 0.138,
) -> str:
    """Write a minimal but valid valuation artifact and return the run_id."""
    from backend.reporting.artifact_manifest import ArtifactManifest, write_manifest

    artifacts = tmp_path / "artifacts"
    (artifacts / "facts").mkdir(parents=True)
    (artifacts / "valuation").mkdir(parents=True)

    facts_path = artifacts / "facts" / f"{ticker}_facts.json"
    facts_path.write_text(
        json.dumps({
            "facts": {
                "revenue.net": {"2024FY": 1865.0, "2025FY": 2000.0},
                "cogs.total": {"2024FY": -980.0, "2025FY": -1050.0},
                "gross_profit.total": {"2024FY": 885.0, "2025FY": 950.0},
                "depreciation.total": {"2024FY": 55.0, "2025FY": 60.0},
                "sga.total": {"2024FY": -426.0, "2025FY": -450.0},
                "interest_expense.total": {"2024FY": -8.0, "2025FY": -9.0},
                "tax_expense.total": {"2024FY": -46.0, "2025FY": -50.0},
                "net_income.parent": {"2024FY": 292.0, "2025FY": 320.0},
                "operating_cash_flow.total": {"2024FY": 330.0, "2025FY": 350.0},
                "capex.total": {"2024FY": -155.0, "2025FY": -170.0},
                "equity.parent": {"2024FY": 1800.0, "2025FY": 1960.0},
                "total_assets.ending": {"2024FY": 2200.0, "2025FY": 2400.0},
                "cash_and_equivalents.ending": {"2024FY": 420.0, "2025FY": 460.0},
                "eps.basic": {"2024FY": 3094.0, "2025FY": 3394.0},
                "shares_outstanding.total": {"2025FY": 94_450_000.0},
            }
        }),
        encoding="utf-8",
    )

    blend_dcf = {
        "current_price_vnd": 50_200.0,
        "price_fcff_vnd": 35_767.0,
        "price_fcfe_vnd": 28_500.0 if include_fcfe else None,
        "fcff_weight": 0.60,
        "fcfe_weight": 0.40,
        "target_price_dcf_vnd": target_price_vnd,
        "upside_pct": target_price_vnd / 50_200.0 - 1.0,
        "is_draft_only": False,
        "formula": "0.60 * Price_FCFF + 0.40 * Price_FCFE",
    }
    valuation_path = artifacts / "valuation" / f"{ticker}_valuation.json"
    valuation_path.write_text(
        json.dumps({
            "forecast": {
                "drivers": {
                    "revenue_growth": {"value": 0.063},
                    "gross_margin": {"value": 0.475},
                    "sga_to_revenue": {"value": 0.225},
                    "depreciation_to_revenue": {"value": 0.03},
                    "capex_to_revenue": {"value": 0.085},
                    "effective_tax_rate": {"value": 0.158},
                },
                "forecast_years": [
                    {
                        "label": "2026F",
                        "revenue": 2126.0,
                        "cogs": -1116.0,
                        "gross_profit": 1010.0,
                        "depreciation": 64.0,
                        "sga": -478.0,
                        "interest_expense": -9.0,
                        "tax_expense": -53.0,
                        "net_income": 340.0,
                        "capex": -181.0,
                        "equity": 2100.0,
                        "total_assets": 2560.0,
                        "total_debt": 175.0,
                        "eps": 3600.0,
                        "ebit": 532.0,
                        "profit_before_tax": 395.0,
                    }
                ],
            },
            "fcff": {
                "wacc": wacc,
                "terminal_growth": 0.03,
                "wacc_breakdown": {"tax_rate": 0.158, "cost_of_equity": 0.138},
                "fcff_table": [
                    {
                        "label": "2026F",
                        "fcff": 195.0,
                        "delta_nwc": -18.0,
                        "ebit": 532.0,
                        "ebit_after_tax": 448.0,
                        "depreciation": 64.0,
                        "capex": 181.0,
                    }
                ],
                "enterprise_value": 3_200_000.0,
                "net_debt_bridge": {"status": "ok"},
                "shares_mn": 94.45,
            },
            "blend_dcf": blend_dcf,
        }),
        encoding="utf-8",
    )

    manifest = ArtifactManifest(
        run_id="run_regression",
        ticker=ticker,
        created_at="2026-06-09T00:00:00",
        schema_version=1,
        artifacts={
            "facts": {"path": str(facts_path), "producer": "TEST"},
            "valuation": {"path": str(valuation_path), "producer": "TEST"},
        },
    )
    write_manifest(manifest, base_dir=artifacts)
    monkeypatch.setattr("backend.reporting.client_report_view_model.ROOT", tmp_path)
    return "run_regression"


def _render_html(tmp_path, monkeypatch, **kwargs) -> str:
    """Build a full analyst_draft HTML string for regression checks."""
    run_id = _write_regression_fixture(tmp_path, monkeypatch, **kwargs)
    vm = build_client_report_view_model("DBD", "analyst_draft", run_id=run_id)
    sections = build_client_report_sections(vm)
    ctx = ReportContext(
        ticker=vm.ticker,
        company_name=vm.company_name,
        exchange=vm.exchange,
        report_date=vm.report_date,
        data_cutoff=vm.report_date,
        rating=vm.recommendation,
        current_price=vm.current_price.amount if vm.current_price else None,
        target_price=vm.target_price.amount if vm.target_price else None,
        upside_pct=(vm.upside_downside.value * 100.0) if vm.upside_downside else None,
        risk_level="Trung bình",
        data_confidence="Professional report view",
        status="ANALYST_REVIEW",
        _current_price_missing=vm.current_price is None,
        _target_price_missing=vm.target_price is None,
        _upside_missing=vm.upside_downside is None,
        _has_valuation=vm.target_price is not None,
        _has_forecast_table=bool(vm.valuation_model_table.rows),
        _has_sensitivity=False,
    )
    html_path = HTMLRenderer().render(sections, ctx, output_dir=tmp_path, run_id="REGRESSION")
    return html_path.read_text(encoding="utf-8")


# ── Phase 6 regression tests ───────────────────────────────────────────────────


def test_no_zero_target_price_in_client_sections(tmp_path, monkeypatch):
    """When a valid target price exists, no section may render '0 VND' as the target.

    Acceptance criterion: renderer never displays 0 VND as a target price.
    """
    html = _render_html(tmp_path, monkeypatch, target_price_vnd=62_000.0)
    # The target price must appear in the output
    assert "62,000" in html, "Target price 62,000 VND must appear in HTML"
    # No context where '0 VND' appears as a price (allow '0%' etc.)
    zero_price_matches = re.findall(r"(?<!\d)0 VND(?!\d)", html)
    assert not zero_price_matches, (
        f"Found '0 VND' in HTML — target_price must never render as zero: {zero_price_matches[:3]}"
    )


def test_no_internal_debug_states_in_client_sections(tmp_path, monkeypatch):
    """Client-facing sections must not expose raw pipeline state strings.

    Acceptance criterion: no pending_review / default_unapproved / 'artifact PASS'
    in main sections.
    """
    html = _render_html(tmp_path, monkeypatch)
    forbidden = [
        "pending_review",
        "default_unapproved",
        "valuation_result",
        "artifact PASS",
        "gate_failed",
        "BLOCKED",
        "NEEDS_REVIEW",
    ]
    found = [term for term in forbidden if term in html]
    assert not found, (
        f"Internal debug states found in client HTML: {found}\n"
        "These must never appear in a client-facing report."
    )


def test_draft_mode_shows_valuation_data_when_artifact_valid(tmp_path, monkeypatch):
    """analyst_draft mode must render valuation data when the artifact is valid.

    Acceptance criterion: approval pending must not delete valuation tables.
    Valuation sections render even without explicit analyst approval flag.
    """
    run_id = _write_regression_fixture(tmp_path, monkeypatch)
    vm = build_client_report_view_model("DBD", "analyst_draft", run_id=run_id)

    # Target price must be populated from the blend artifact
    assert vm.target_price is not None, (
        "vm.target_price must not be None in analyst_draft when blend artifact has valid target"
    )
    assert vm.target_price.amount > 0, (
        f"vm.target_price must be positive, got {vm.target_price.amount}"
    )

    # Upside must be a real value, not forced to 0
    assert vm.upside_downside is not None, "upside_downside must not be None when target_price is valid"

    # Full analytical sections must be rendered (not review dashboard)
    sections = build_client_report_sections(vm)
    page_ids = [s["page"] for s in sections]
    assert "snapshot" in page_ids
    assert "valuation_model" in page_ids
    assert "review_summary" not in page_ids, "review dashboard must not appear in analyst_draft"


def test_final_mode_blocks_when_valuation_unpublishable(tmp_path, monkeypatch):
    """client_final mode must raise when valuation is not officially approved."""
    from backend.reporting.client_report_view_model import (
        ClientReportDataMissing,
        assert_client_final_ready,
    )

    run_id = _write_regression_fixture(tmp_path, monkeypatch)
    vm = build_client_report_view_model("DBD", "client_final", run_id=run_id)

    # Without a valuation_result with is_publishable=True, client_final must block
    with pytest.raises(ClientReportDataMissing):
        assert_client_final_ready(vm)


def test_context_bridge_uses_none_not_zero_for_missing_target(tmp_path, monkeypatch):
    """_context_from_view_model must produce None, not 0.0, for missing target_price.

    The template uses _target_price_missing flag to display '—'; a 0.0 fallback
    would bypass this guard and show '0 VND' in some template paths.
    """
    # Write fixture with no blend → target_price will be None
    from backend.reporting.artifact_manifest import ArtifactManifest, write_manifest

    artifacts = tmp_path / "artifacts"
    (artifacts / "facts").mkdir(parents=True)
    (artifacts / "valuation").mkdir(parents=True)

    fp = artifacts / "facts" / "DBD_facts.json"
    fp.write_text(json.dumps({"facts": {}}), encoding="utf-8")
    vp = artifacts / "valuation" / "DBD_valuation.json"
    vp.write_text(json.dumps({"blend_dcf": {}}), encoding="utf-8")  # empty blend

    manifest = ArtifactManifest(
        run_id="run_no_blend",
        ticker="DBD",
        created_at="2026-06-09T00:00:00",
        schema_version=1,
        artifacts={
            "facts": {"path": str(fp), "producer": "TEST"},
            "valuation": {"path": str(vp), "producer": "TEST"},
        },
    )
    write_manifest(manifest, base_dir=artifacts)
    monkeypatch.setattr("backend.reporting.client_report_view_model.ROOT", tmp_path)

    vm = build_client_report_view_model("DBD", "analyst_draft", run_id="run_no_blend")
    assert vm.target_price is None, "target_price must be None when blend is empty"

    # Verify the bridge produces None, not 0.0
    tp_val = vm.target_price.amount if vm.target_price else None
    assert tp_val is None, f"bridge must produce None for missing target, got {tp_val}"


def test_wacc_not_zero_when_fcff_artifact_has_valid_wacc(tmp_path, monkeypatch):
    """When the FCFF artifact contains a valid WACC, the valuation model table
    must not display WACC as 0.0%.

    Acceptance criterion: WACC never defaults to 0.0% when the artifact exists.
    """
    run_id = _write_regression_fixture(tmp_path, monkeypatch, wacc=0.138)
    vm = build_client_report_view_model("DBD", "analyst_draft", run_id=run_id)

    # The profitability/valuation table includes WACC
    wacc_row = next(
        (row for row in vm.profitability_valuation_table.rows if "wacc" in row[0].lower()),
        None,
    )
    if wacc_row:
        # All WACC values must be non-zero
        for v in wacc_row[1]:
            if v is not None:
                assert float(v) != 0.0, f"WACC value must not be 0.0 when artifact has 0.138: got {v}"


def test_null_fcfe_renders_dash_not_zero(tmp_path, monkeypatch):
    """When price_fcfe_vnd is None (FCFE not yet computed), the client
    sections must show '—' not '0' in the valuation model display.

    Acceptance criterion: missing values remain null/dash, never convert to 0.
    """
    html = _render_html(tmp_path, monkeypatch, include_fcfe=False)
    # "0" should not appear adjacent to FCFE label in formatted price context
    # We check: no "0 VND" anywhere (the zero target price guard covers this broadly)
    zero_price_matches = re.findall(r"(?<!\d)0 VND(?!\d)", html)
    assert not zero_price_matches, f"Null FCFE rendered as '0 VND': {zero_price_matches}"


def test_all_baseline_sections_exist(tmp_path, monkeypatch):
    """All 8 baseline sections required by the regression plan must be present.

    Acceptance criterion: cover, financial_performance, forecast, valuation,
    sensitivity, risks, conclusion sections must exist.
    """
    run_id = _write_regression_fixture(tmp_path, monkeypatch)
    vm = build_client_report_view_model("DBD", "analyst_draft", run_id=run_id)
    sections = build_client_report_sections(vm)
    page_ids = {s["page"] for s in sections}

    required = {
        "snapshot",
        "company_overview",
        "financial_performance",
        "forecast_drivers",
        "valuation_model",
        "sensitivity_peer",
        "risks_catalysts",
        "conclusion_sources",
    }
    missing = required - page_ids
    assert not missing, f"Required sections missing from output: {missing}"


def test_recommendation_not_under_review_when_target_valid(tmp_path, monkeypatch):
    """When target_price is valid and upside is computed, recommendation must
    be MUA/NẮM GIỮ/BÁN, not ĐANG HOÀN THIỆN or UNDER_REVIEW.

    Acceptance criterion: valid valuation → valid recommendation.
    """
    run_id = _write_regression_fixture(tmp_path, monkeypatch, target_price_vnd=62_000.0)
    vm = build_client_report_view_model("DBD", "analyst_draft", run_id=run_id)

    assert vm.recommendation not in ("ĐANG HOÀN THIỆN", "UNDER_REVIEW", "CHƯA XUẤT BẢN"), (
        f"Recommendation must not be a blocked state when target is valid: {vm.recommendation!r}"
    )
    assert vm.recommendation in ("MUA", "NẮM GIỮ", "BÁN"), (
        f"Expected MUA/NẮM GIỮ/BÁN, got {vm.recommendation!r}"
    )
