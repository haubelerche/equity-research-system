from __future__ import annotations

import pytest

from backend.reporting.client_report_view_model import (
    ClientReportDataMissing,
    assert_client_final_ready,
    build_client_report_view_model,
)
from backend.reporting.client_section_builder import build_client_report_sections
from backend.reporting.html_renderer import HTMLRenderer
from backend.reporting.pdf_renderer import CLIENT_FORBIDDEN_PDF_TERMS, preflight_forbidden_terms
from backend.reporting.section_builder import ReportContext
from backend.reporting.section_builder import REPORT_SECTION_CONTRACTS, section_coherence_gate


def _write_client_fixture(tmp_path, monkeypatch, ticker: str, publishable: bool = False) -> str:
    import json
    from backend.reporting.artifact_manifest import ArtifactManifest, write_manifest

    artifacts = tmp_path / "artifacts"
    facts_dir = artifacts / "facts"
    valuation_dir = artifacts / "valuation"
    facts_dir.mkdir(parents=True, exist_ok=True)
    valuation_dir.mkdir(parents=True, exist_ok=True)

    facts_path = facts_dir / f"{ticker}_facts.json"
    facts_path.write_text(
        json.dumps({
            "facts": {
                "revenue.net": {"2024FY": 1000.0, "2025FY": 1100.0},
                "cogs.total": {"2024FY": -520.0, "2025FY": -560.0},
                "gross_profit.total": {"2024FY": 480.0, "2025FY": 540.0},
                "depreciation.total": {"2024FY": 30.0, "2025FY": 35.0},
                "sga.total": {"2024FY": -220.0, "2025FY": -240.0},
                "interest_expense.total": {"2024FY": -10.0, "2025FY": -12.0},
                "tax_expense.total": {"2024FY": -35.0, "2025FY": -38.0},
                "net_income.parent": {"2024FY": 180.0, "2025FY": 205.0},
                "operating_cash_flow.total": {"2024FY": 210.0, "2025FY": 230.0},
                "capex.total": {"2024FY": -70.0, "2025FY": -80.0},
                "free_cash_flow.total": {"2024FY": 140.0, "2025FY": 150.0},
                "equity.parent": {"2024FY": 900.0, "2025FY": 1000.0},
                "total_assets.ending": {"2024FY": 1500.0, "2025FY": 1650.0},
                "cash_and_equivalents.ending": {"2024FY": 120.0, "2025FY": 140.0},
                "short_term_debt.ending": {"2024FY": 100.0, "2025FY": 110.0},
                "eps.basic": {"2024FY": 1600.0, "2025FY": 1800.0},
                "shares_outstanding.total": {"2025FY": 100000000.0}
            }
        }),
        encoding="utf-8",
    )

    valuation_path = valuation_dir / f"{ticker}_valuation.json"
    valuation_path.write_text(
        json.dumps({
            "forecast": {
                "drivers": {
                    "revenue_growth": {"value": 0.08},
                    "gross_margin": {"value": 0.47},
                    "sga_to_revenue": {"value": 0.22},
                    "depreciation_to_revenue": {"value": 0.03},
                    "capex_to_revenue": {"value": 0.08},
                    "effective_tax_rate": {"value": 0.158}
                },
                "forecast_years": [
                    {
                        "label": "2026F",
                        "revenue": 1188.0,
                        "cogs": -629.6,
                        "gross_profit": 558.4,
                        "depreciation": 35.6,
                        "sga": -261.4,
                        "interest_expense": -12.0,
                        "tax_expense": -45.0,
                        "net_income": 240.0,
                        "capex": -95.0,
                        "equity": 1100.0,
                        "total_assets": 1750.0,
                        "total_debt": 100.0,
                        "eps": 2100.0,
                        "ebit": 297.0,
                        "profit_before_tax": 285.0
                    }
                ]
            },
            "fcff": {
                "wacc": 0.12,
                "terminal_growth": 0.03,
                "wacc_breakdown": {"tax_rate": 0.158, "cost_of_equity": 0.138},
                "fcff_table": [{"label": "2026F", "fcff": 190.0, "delta_nwc": -20.0}]
            },
            "blend_dcf": {
                "current_price_vnd": 50000.0,
                "target_price_dcf_vnd": 62000.0,
                "upside_pct": 0.24
            }
        }),
        encoding="utf-8",
    )

    manifest_artifacts = {
        "facts": {"path": str(facts_path), "producer": "TEST"},
        "valuation": {"path": str(valuation_path), "producer": "TEST"},
    }

    # Publishable variant: a usable valuation_result (single source of truth for
    # target price) so the full 8-page analytical report renders. Without it the
    # display gate forces target_price=None and the review dashboard renders.
    if publishable:
        vr_dir = artifacts / "valuation_results"
        vr_dir.mkdir(parents=True, exist_ok=True)
        vr_path = vr_dir / f"20260601_{ticker}_valuation_result.json"
        vr_path.write_text(
            json.dumps({
                "ticker": ticker,
                "is_publishable": True,
                "current_price": 50000.0,
                "target_price": 62000.0,
                "upside_downside": 0.24,
            }),
            encoding="utf-8",
        )
        manifest_artifacts["valuation_result"] = {"path": str(vr_path), "producer": "TEST"}

    run_id = "run_client_contract_fixture"
    manifest = ArtifactManifest(
        run_id=run_id,
        ticker=ticker,
        created_at="2026-06-01T00:00:00",
        schema_version=1,
        artifacts=manifest_artifacts,
    )
    write_manifest(manifest, base_dir=artifacts)
    monkeypatch.setattr("backend.reporting.client_report_view_model.ROOT", tmp_path)
    return run_id


def _client_html_text(tmp_path, monkeypatch, ticker: str = "DBD", publishable: bool = False) -> str:
    run_id = _write_client_fixture(tmp_path, monkeypatch, ticker, publishable=publishable)
    vm = build_client_report_view_model(
        ticker,
        "analyst_draft",
        run_id=run_id,
    )
    sections = build_client_report_sections(vm)
    ctx = ReportContext(
        ticker=vm.ticker,
        company_name=vm.company_name,
        exchange=vm.exchange,
        report_date=vm.report_date,
        data_cutoff=vm.report_date,
        rating=vm.recommendation,
        current_price=vm.current_price.amount if vm.current_price else 0,
        target_price=vm.target_price.amount if vm.target_price else 0,
        upside_pct=vm.upside_downside.value * 100 if vm.upside_downside else 0,
        risk_level="Trung bình",
        data_confidence="Professional report view",
        status="ANALYST_REVIEW",
    )
    html_path = HTMLRenderer().render(sections, ctx, output_dir=tmp_path, run_id="CONTRACT")
    return html_path.read_text(encoding="utf-8")


def test_analyst_draft_has_no_backend_terms_in_sections(tmp_path, monkeypatch):
    # Non-publishable draft → review dashboard; must still be free of backend jargon.
    html = _client_html_text(tmp_path, monkeypatch)
    preflight_forbidden_terms(html, CLIENT_FORBIDDEN_PDF_TERMS)


def test_analyst_draft_always_renders_full_analytical_report(tmp_path, monkeypatch):
    """analyst_draft always renders the full analytical report, even when valuation
    is not officially publishable. Review dashboard only applies to client_final mode."""
    run_id = _write_client_fixture(tmp_path, monkeypatch, "DBD", publishable=False)
    vm = build_client_report_view_model("DBD", "analyst_draft", run_id=run_id)
    sections = build_client_report_sections(vm)
    page_names = [s["page"] for s in sections]
    assert page_names[0] == "snapshot"  # full analytical report
    assert "review_summary" not in page_names  # NOT the review dashboard
    html = _client_html_text(tmp_path, monkeypatch)
    assert "CẦN CHUYÊN VIÊN RÀ SOÁT" not in html  # review dashboard not shown in analyst_draft
    preflight_forbidden_terms(html, CLIENT_FORBIDDEN_PDF_TERMS)


def test_table_has_data_detects_all_dash_table():
    from backend.reporting.client_section_builder import _table_has_data
    from backend.reporting.client_report_view_model import TableData

    empty = TableData(title="X", periods=["2025A"], rows=[("Doanh thu", [None]), ("EPS", ["—"])])
    full = TableData(title="X", periods=["2025A"], rows=[("Doanh thu", [None]), ("EPS", [1800.0])])
    assert _table_has_data(empty) is False
    assert _table_has_data(full) is True


def test_review_dashboard_omits_all_dash_financial_table(tmp_path, monkeypatch):
    """When no canonical facts exist, the review dashboard must not render a table
    of all dashes — it shows a data-inventory note instead."""
    from backend.reporting.client_section_builder import _review_dashboard_pages
    vm = build_client_report_view_model(
        "DBD", "analyst_draft",
        run_id=_write_client_fixture(tmp_path, monkeypatch, "DBD"),
    )
    # Force an all-empty financial table to simulate a DB-less run with no facts.
    n = len(vm.financial_summary_table.periods)
    vm.financial_summary_table.rows[:] = [
        (label, [None] * n) for label, _ in vm.financial_summary_table.rows
    ]
    html = "".join(p[2] for p in _review_dashboard_pages(vm))
    assert "chưa được nạp đầy đủ" in html
    assert "financial-model-table" not in html


def test_analyst_draft_html_shows_recommendation_banner(tmp_path, monkeypatch):
    # analyst_draft always renders the full report with the recommendation banner
    html = _client_html_text(tmp_path, monkeypatch)
    assert '<div class="recommendation-card' in html  # rating banner always present in analyst_draft


def test_publishable_report_keeps_recommendation_banner(tmp_path, monkeypatch):
    html = _client_html_text(tmp_path, monkeypatch, publishable=True)
    assert '<div class="recommendation-card' in html


def test_publishable_draft_contains_required_imp_style_tables(tmp_path, monkeypatch):
    html = _client_html_text(tmp_path, monkeypatch, publishable=True)
    required_terms = [
        "financial-model-table",
        "Doanh thu",
        "EBITDA",
        "EBIT",
        "ROE",
        "ROA",
        "ROIC",
        "WACC",
        "EV/EBITDA",
        "P/B",
        "P/S",
    ]
    for term in required_terms:
        assert term in html


def test_client_renderer_uses_eight_page_contract(tmp_path, monkeypatch):
    run_id = _write_client_fixture(tmp_path, monkeypatch, "DBD", publishable=True)
    vm = build_client_report_view_model("DBD", "analyst_draft", run_id=run_id)
    sections = build_client_report_sections(vm)

    assert [s["page"] for s in sections] == [
        "snapshot",
        "company_overview",
        "financial_performance",
        "forecast_drivers",
        "valuation_model",
        "sensitivity_peer",
        "risks_catalysts",
        "conclusion_sources",
    ]
    assert len(sections) == 8


def test_section_contract_and_coherence_gate_detect_leakage():
    assert set(REPORT_SECTION_CONTRACTS) == {
        "snapshot",
        "company_overview",
        "financial_performance",
        "forecast_drivers",
        "valuation_model",
        "sensitivity_peer",
        "risks_catalysts",
        "conclusion_sources",
    }

    sections = [
        {"page": "company_overview", "markdown": "Target price and WACC belong elsewhere."},
        {"page": "valuation_model", "markdown": "FCFF bridge and target price are coherent here."},
    ]
    gate = section_coherence_gate(sections)
    assert gate["status"] == "FAIL"
    assert gate["violations"][0]["reason"] == "valuation_content_in_business_section"


def test_analyst_draft_has_no_encoding_corruption_markers(tmp_path, monkeypatch):
    html = _client_html_text(tmp_path, monkeypatch)
    forbidden_markers = ["\ufffd", "\u00ef\u00bf\u00bd", "Gi\u00ef", "Ch?", "B->o", "c->o"]
    for marker in forbidden_markers:
        assert marker not in html
    assert ">?</" not in html


def test_non_mvp_universe_ticker_can_render_analyst_draft_fixture(tmp_path, monkeypatch):
    html = _client_html_text(tmp_path, monkeypatch, ticker="DP3", publishable=True)
    assert "DP3" in html
    assert "Dược phẩm" in html
    assert "financial-model-table" in html
    assert "\ufffd" not in html


def test_analyst_draft_preserves_driver_based_calculations(tmp_path, monkeypatch):
    html = _client_html_text(tmp_path, monkeypatch, publishable=True)
    required_terms = [
        "DRIVER",
        "Target price",
        "Revenue growth stress",
        "Gross margin stress",
        "GMP-EU",
        "Capex / doanh thu",
        "12.0%",
        "EPS",
        "PEG",
    ]
    for term in required_terms:
        assert term in html, f"Expected {term!r} in HTML"

    # When no dividend fact exists for a ticker, the value must be "—" (not a raw float).
    # This verifies the correct new behavior: missing facts render as a dash placeholder.
    assert "2000.0" not in html, "Raw dividend float must not appear in rendered HTML"
    assert '<td class="numeric">2,000</td>' not in html, "Hardcoded DHG dividend must not appear for DBD"


def test_client_final_fails_when_required_valuation_is_missing(tmp_path, monkeypatch):
    # Point artifact resolution at an empty directory so NO valuation/forecast/snapshot
    # artifacts resolve — this deterministically reproduces the "valuation missing" state
    # regardless of what real runs have written under artifacts/.
    import backend.reporting.client_report_view_model as vm_mod
    monkeypatch.setattr(vm_mod, "ROOT", tmp_path)

    vm = build_client_report_view_model(
        "DBD",
        "client_final",
        allow_latest_artifacts=True,
    )
    with pytest.raises(ClientReportDataMissing) as exc:
        assert_client_final_ready(vm)
    # With no valuation artifact, the model-derived target price / upside are absent,
    # so the client-final export must be blocked.
    assert "target_price" in exc.value.missing_fields
    assert "upside_downside" in exc.value.missing_fields


def test_build_client_report_view_model_accepts_run_id():
    """build_client_report_view_model must accept run_id kwarg."""
    import inspect
    from backend.reporting.client_report_view_model import build_client_report_view_model
    sig = inspect.signature(build_client_report_view_model)
    assert "run_id" in sig.parameters
    assert "allow_latest_artifacts" in sig.parameters


def test_build_client_report_view_model_uses_manifest_not_glob(tmp_path, monkeypatch):
    """With run_id, build_client_report_view_model must read manifest path, not glob latest."""
    import json
    from backend.reporting.artifact_manifest import ArtifactManifest, write_manifest

    artifacts = tmp_path / "artifacts"
    val_dir = artifacts / "valuation"
    val_dir.mkdir(parents=True)

    # Specific file (manifest points here)
    specific_val = val_dir / "DHG_specific_valuation.json"
    specific_val.write_text(json.dumps({"MARKER": "manifest_file", "ratios": {}}), encoding="utf-8")

    # Newer file (glob would pick this)
    wrong_val = val_dir / "DHG_zzz_valuation.json"
    wrong_val.write_text(json.dumps({"MARKER": "glob_file", "ratios": {}}), encoding="utf-8")

    manifest = ArtifactManifest(
        run_id="run_vm_manifest_test",
        ticker="DHG",
        created_at="2026-06-01T00:00:00",
        schema_version=1,
        artifacts={"valuation": {"path": str(specific_val), "producer": "VALUATION_RUN"}},
    )
    write_manifest(manifest, base_dir=artifacts)
    monkeypatch.setattr("backend.reporting.client_report_view_model.ROOT", tmp_path)

    # Track file reads
    import builtins
    reads: list[str] = []
    original_open = builtins.open

    def tracking_open(path, *args, **kw):
        reads.append(str(path))
        return original_open(path, *args, **kw)

    monkeypatch.setattr(builtins, "open", tracking_open)

    from backend.reporting.client_report_view_model import build_client_report_view_model
    build_client_report_view_model("DHG", "analyst_draft", run_id="run_vm_manifest_test")

    # The wrong (glob-latest) file must NOT have been opened for valuation
    wrong_reads = [r for r in reads if "zzz" in r and "valuation" in r]
    assert not wrong_reads, (
        f"view model opened the glob-latest file instead of the manifest file: {wrong_reads}"
    )


def test_view_model_uses_nested_valuation_subartifacts_when_manifest_only_has_valuation(tmp_path, monkeypatch):
    """A run manifest with only valuation JSON must still provide forecast/fcff/blend data."""
    import json
    from backend.reporting.artifact_manifest import ArtifactManifest, write_manifest

    artifacts = tmp_path / "artifacts"
    val_dir = artifacts / "valuation"
    result_dir = artifacts / "valuation_results"
    val_dir.mkdir(parents=True)
    result_dir.mkdir(parents=True)
    valuation_path = val_dir / "DHG_run_valuation.json"
    valuation_path.write_text(
        json.dumps({
            "forecast": {"forecast_years": [{"label": "2026F", "revenue": 1000}]},
            "fcff": {"fcff_table": [{"label": "2026F", "fcff": 100}]},
            "blend_dcf": {"current_price_vnd": 10000, "target_price_dcf_vnd": 12000},
        }),
        encoding="utf-8",
    )
    result_path = result_dir / "run_DHG_valuation_result.json"
    result_path.write_text(
        json.dumps({
            "ticker": "DHG",
            "current_price": 10000,
            "target_price": 12000,
            "upside_downside": 0.2,
            "is_publishable": True,
        }),
        encoding="utf-8",
    )
    manifest = ArtifactManifest(
        run_id="run_vm_nested_test",
        ticker="DHG",
        created_at="2026-06-01T00:00:00",
        schema_version=1,
        artifacts={
            "valuation": {"path": str(valuation_path), "producer": "VALUATION_RUN"},
            "valuation_result": {"path": str(result_path), "producer": "VALUATION_RUN"},
        },
    )
    write_manifest(manifest, base_dir=artifacts)
    monkeypatch.setattr("backend.reporting.client_report_view_model.ROOT", tmp_path)

    vm = build_client_report_view_model("DHG", "analyst_draft", run_id="run_vm_nested_test")

    assert "forecast_years" not in vm.missing_required_fields
    assert "fcff_table" not in vm.missing_required_fields
    assert vm.target_price is not None


def test_no_hardcoded_dhg_shares_in_source():
    """Module must not contain hardcoded DHG share count 109.1773."""
    import inspect
    from backend.reporting import client_report_view_model as m
    src = inspect.getsource(m)
    assert "109.1773" not in src, "109.1773 is DHG share count — must come from facts"


def test_no_hardcoded_dividend_constant_in_source():
    """Module must not contain _DIVIDEND_PER_SHARE = 2000.0 as a module constant."""
    import inspect
    from backend.reporting import client_report_view_model as m
    src = inspect.getsource(m)
    assert "_DIVIDEND_PER_SHARE = 2000.0" not in src, (
        "_DIVIDEND_PER_SHARE = 2000.0 is DHG-specific — must come from facts per ticker"
    )


def test_periods_not_a_hardcoded_five_year_literal():
    """_PERIODS must not be a fixed literal like ['2021F', ..., '2025F']."""
    import inspect
    from backend.reporting import client_report_view_model as m
    src = inspect.getsource(m)
    # Check the literal that was originally there
    assert '["2021F", "2022F", "2023F", "2024F", "2025F"]' not in src, (
        "_PERIODS must be derived from available fact periods"
    )


def test_view_model_fails_when_run_id_manifest_missing():
    """Explicit run_id must not fall back to glob when the manifest is missing."""
    import pytest
    from backend.reporting.client_report_view_model import build_client_report_view_model

    with pytest.raises(FileNotFoundError, match="artifact manifest"):
        build_client_report_view_model("DHG", "analyst_draft", run_id="run_nonexistent_manifest_xyz")


def test_view_model_requires_run_id_unless_debug_fallback(monkeypatch):
    """Implicit latest-artifact resolution must be an explicit debug choice."""
    import pytest
    monkeypatch.setattr("backend.reporting.client_report_view_model.ROOT",
                        __import__("pathlib").Path("/nonexistent_path_xyz"))

    with pytest.raises(ValueError, match="run_id is required"):
        build_client_report_view_model("DHG", "analyst_draft")

    vm = build_client_report_view_model(
        "DHG",
        "analyst_draft",
        allow_latest_artifacts=True,
    )
    assert vm.ticker == "DHG"
