"""Tests for Phase 7: ReportArtifact, LayoutRenderAudit, ExportGateResult."""
from __future__ import annotations

import json
import pytest

from backend.reporting.report_artifact import (
    ReportArtifact,
    ReportSection,
    make_section,
    SECTION_IDS,
)
from backend.reporting.layout_audit import (
    run_layout_audit,
    LayoutRenderAudit,
    AuditIssue,
)
from backend.reporting.export_gate import (
    evaluate_export_gate,
    ExportGateResult,
    GateResult,
    _source_gate,
    _forecast_gate,
    _valuation_gate,
    _sensitivity_gate,
    _citation_gate_from_ledger,
    _human_review_gate,
    _layout_gate_from_audit,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _section(sid: str, words: int = 100, html: str = "") -> ReportSection:
    # Use sid as seed so each section has unique content (avoids duplicate detection)
    filler = f" {sid}-content unique-{sid} " * (words // 4 + 1)
    content = html or filler
    return ReportSection(
        section_id=sid, section_title=sid.title(),
        html_content=content, word_count=words,
        has_tables=False, has_charts=False,
    )


def _full_artifact(render_mode: str = "analyst_draft") -> ReportArtifact:
    """ReportArtifact with all required sections populated."""
    return ReportArtifact(
        report_id="test_001",
        ticker="TST",
        run_id="20260604",
        report_date="2026-06-04",
        render_mode=render_mode,  # type: ignore[arg-type]
        sections=[_section(sid, 150) for sid in SECTION_IDS],
        target_price_vnd=30_000.0,
        current_price_vnd=25_000.0,
    )


# ── ReportArtifact ────────────────────────────────────────────────────────────

class TestReportArtifact:
    def test_missing_sections_detected(self):
        art = ReportArtifact(
            report_id="r1", ticker="TST", run_id="ts",
            report_date="2026-06-04", render_mode="analyst_draft",
            sections=[_section("snapshot")],
        )
        missing = art.missing_sections
        assert "company_overview" in missing
        assert "snapshot" not in missing

    def test_total_word_count(self):
        art = _full_artifact()
        assert art.total_word_count == 150 * len(SECTION_IDS)

    def test_all_missing_data_flags_aggregated(self):
        sec = _section("snapshot")
        sec.missing_data_flags = ["dividend_yield", "shares_outstanding"]
        art = ReportArtifact(
            report_id="r1", ticker="TST", run_id="ts",
            report_date="2026-06-04", render_mode="analyst_draft",
            sections=[sec],
        )
        flags = art.all_missing_data_flags
        assert "snapshot:dividend_yield" in flags

    def test_to_dict_serializable(self):
        art = _full_artifact()
        json.dumps(art.to_dict())

    def test_make_section_counts_words(self):
        sec = make_section("val", "Valuation", "<p>Hello world this is text</p>")
        assert sec.word_count == 5

    def test_make_section_detects_tables(self):
        sec = make_section("fin", "Financial", "<table><tr><td>data</td></tr></table>")
        assert sec.has_tables is True

    def test_make_section_detects_charts(self):
        sec = make_section("chart", "Charts", "<p>see chart</p>",
                           chart_ids=["C1_price"])
        assert sec.has_charts is True
        assert "C1_price" in sec.chart_ids


# ── LayoutRenderAudit ─────────────────────────────────────────────────────────

class TestLayoutAudit:
    def test_no_issues_for_complete_artifact(self):
        art = _full_artifact()
        audit = run_layout_audit(art)
        errors = [i for i in audit.issues if i.severity == "error"
                  and i.check_name == "missing_section"]
        assert errors == []

    def test_missing_section_is_error(self):
        # Missing sections only flagged on client_final (not blocked/draft reports)
        art = ReportArtifact(
            report_id="r1", ticker="TST", run_id="ts",
            report_date="2026-06-04", render_mode="client_final",
            sections=[_section("snapshot", 150)],
        )
        audit = run_layout_audit(art)
        assert audit.layout_gate_status == "FAIL"
        assert any(i.check_name == "missing_section" for i in audit.errors)

    def test_missing_section_ignored_for_draft(self):
        # Blocked/draft reports have different structure — missing sections not an error
        art = ReportArtifact(
            report_id="r1", ticker="TST", run_id="ts",
            report_date="2026-06-04", render_mode="analyst_draft",
            sections=[_section("snapshot", 150)],
        )
        audit = run_layout_audit(art)
        assert not any(i.check_name == "missing_section" for i in audit.errors)

    def test_empty_section_under_30_words_is_error(self):
        art = ReportArtifact(
            report_id="r1", ticker="TST", run_id="ts",
            report_date="2026-06-04", render_mode="analyst_draft",
            sections=[_section(sid, 150 if sid != "valuation_model" else 5)
                      for sid in SECTION_IDS],
        )
        audit = run_layout_audit(art)
        assert any(
            i.check_name == "empty_section" and i.section_id == "valuation_model"
            for i in audit.errors
        )

    def test_duplicate_content_is_error(self):
        # Two sections with identical html → duplicate detection should fire
        same_html = "<p>" + "word " * 60 + "</p>"
        sections = [_section(sid, 60) for sid in SECTION_IDS]
        # Force first two sections to share identical html
        sections[0] = ReportSection("snapshot", "Snapshot", same_html, 60, False, False)
        sections[1] = ReportSection("company_overview", "Company", same_html, 60, False, False)
        art = ReportArtifact(
            report_id="r1", ticker="TST", run_id="ts",
            report_date="2026-06-04", render_mode="analyst_draft",
            sections=sections,
        )
        audit = run_layout_audit(art)
        assert any(i.check_name == "duplicate_section_content" for i in audit.errors)

    def test_backend_term_blocked_in_client_final(self):
        sec = _section("snapshot", 150,
                       html="<p>fact_id=abc123 " + "word " * 50 + "</p>")
        art = ReportArtifact(
            report_id="r1", ticker="TST", run_id="ts",
            report_date="2026-06-04", render_mode="client_final",
            sections=[sec] + [_section(sid, 150) for sid in SECTION_IDS if sid != "snapshot"],
        )
        audit = run_layout_audit(art)
        assert any(i.check_name == "backend_term_in_client_report" for i in audit.errors)

    def test_backend_term_not_blocked_in_draft(self):
        sec = _section("snapshot", 150, html="<p>fact_id=abc " + "word " * 50 + "</p>")
        art = ReportArtifact(
            report_id="r1", ticker="TST", run_id="ts",
            report_date="2026-06-04", render_mode="analyst_draft",
            sections=[sec] + [_section(sid, 150) for sid in SECTION_IDS if sid != "snapshot"],
        )
        audit = run_layout_audit(art)
        assert not any(i.check_name == "backend_term_in_client_report" for i in audit.issues)

    def test_unregistered_chart_is_error(self):
        sec = ReportSection(
            section_id="valuation_model", section_title="Valuation",
            html_content="<p>" + "word " * 60 + "</p>",
            word_count=60, has_tables=False, has_charts=True,
            chart_ids=["C5_missing"],
        )
        art = ReportArtifact(
            report_id="r1", ticker="TST", run_id="ts",
            report_date="2026-06-04", render_mode="analyst_draft",
            sections=[sec] + [_section(sid, 150) for sid in SECTION_IDS if sid != "valuation_model"],
            charts={},  # chart not registered
        )
        audit = run_layout_audit(art)
        assert any(i.check_name == "unregistered_chart" for i in audit.errors)

    def test_vietnamese_font_missing_is_error(self):
        html = "<html><body>Doanh thu tăng trưởng mạnh</body></html>"
        art = _full_artifact()
        audit = run_layout_audit(art, html_full=html)
        assert any(i.check_name == "missing_vietnamese_font" for i in audit.errors)

    def test_vietnamese_font_present_passes(self):
        html = "<html><style>@font-face { font-family: 'Be Vietnam' }</style><body>Nội dung</body></html>"
        art = _full_artifact()
        audit = run_layout_audit(art, html_full=html)
        assert not any(i.check_name == "missing_vietnamese_font" for i in audit.issues)

    def test_layout_gate_pass_when_no_errors(self):
        art = _full_artifact()
        audit = run_layout_audit(art)
        assert audit.layout_gate_status == "PASS"

    def test_to_dict_serializable(self):
        art = _full_artifact()
        audit = run_layout_audit(art)
        json.dumps(audit.to_dict())


# ── ExportGateResult ──────────────────────────────────────────────────────────

class TestExportGate:
    def _run(self, **kwargs) -> ExportGateResult:
        art = _full_artifact()
        return evaluate_export_gate(art, **kwargs)

    def test_all_skip_gives_draft_due_to_human_review(self):
        result = self._run()
        # human_review_gate always FAIL when approval_status=None
        assert result.is_final_exportable is False
        assert result.render_mode == "analyst_draft"
        assert "human_review_gate" in result.blocking_gates

    def test_human_approved_but_forecast_missing_stays_draft(self):
        """forecast_gate and valuation_gate are BLOCKED when no artifacts provided."""
        result = self._run(approval_status="approved")
        # forecast_gate and valuation_gate BLOCK when artifacts absent
        assert "forecast_gate" in result.blocking_gates
        assert "valuation_gate" in result.blocking_gates
        assert result.is_final_exportable is False

    def test_all_required_artifacts_plus_approval_gives_exportable(self):
        """Full exportable path: all gate inputs present and valid + approval."""
        art = _full_artifact()
        # Minimal passing valuation artifact
        val = {
            "fcff": {"net_debt_bridge": {"status": "ok"}, "shares_mn": 94.45,
                     "wacc": 0.13, "terminal_growth": 0.03},
            "blend_dcf": {"is_draft_only": False, "target_price_dcf": 30_000.0,
                          "price_fcff": 35_000.0, "price_fcfe": 22_000.0},
            "fcff_sensitivity": {
                "base_wacc": 0.13, "wacc_range": [0.11, 0.12, 0.13, 0.14, 0.15],
                "matrix": {"0.130": {"0.03": 30_000}},
            },
        }
        # Minimal passing forecast artifact
        fc = {
            "debt_schedule": {"is_fcfe_publishable": True, "forecast_method": "zero_debt_policy"},
            "working_capital_schedule": {"ar_days": 90},
            "forecast_years": [],
        }
        # SKIP gates now block export — all optional gates must be supplied
        source = {"untraced_valuation_facts": [], "tier3_only_valuation_facts": []}
        reconciliation = {"material_conflicts": []}
        ledger = {"summary": {"unsupported": 0, "supported": 10}}
        audit = run_layout_audit(art)
        result = evaluate_export_gate(
            art,
            valuation_artifact=val,
            forecast_artifact=fc,
            source_manifest=source,
            reconciliation_artifact=reconciliation,
            claim_ledger=ledger,
            layout_audit=audit,
            approval_status="approved",
        )
        assert result.is_final_exportable is True
        assert result.render_mode == "client_final"

    def test_valuation_gate_fails_when_blend_draft(self):
        val = {"blend_dcf": {"is_draft_only": True, "valuation_gap_pct": 0.60},
               "fcff": {}}
        g = _valuation_gate(val)
        assert g.status == "FAIL"
        assert any("draft" in i.lower() for i in g.issues)

    def test_valuation_gate_fails_when_net_debt_blocked(self):
        val = {"fcff": {"net_debt_bridge": {"status": "blocked"}}, "blend_dcf": {}}
        g = _valuation_gate(val)
        assert g.status == "FAIL"
        assert any("total_debt" in i for i in g.issues)

    def test_forecast_gate_fails_when_debt_not_publishable(self):
        fc = {"debt_schedule": {"is_fcfe_publishable": False,
                                "fcfe_block_reason": "target_debt_ratio"}}
        g = _forecast_gate(fc)
        assert g.status == "FAIL"

    def test_forecast_gate_blocked_when_missing(self):
        g = _forecast_gate(None)
        assert g.status == "BLOCKED"

    def test_sensitivity_gate_fails_when_base_wacc_missing_from_range(self):
        val = {
            "fcff_sensitivity": {
                "base_wacc": 0.138,
                "wacc_range": [0.08, 0.09, 0.10, 0.11, 0.12],  # 0.138 not present
                "matrix": {"0.080": {}},
            }
        }
        g = _sensitivity_gate(val)
        assert g.status == "FAIL"
        assert any("not in sensitivity" in i.lower() or "base" in i.lower() for i in g.issues)

    def test_sensitivity_gate_passes_when_base_in_range(self):
        val = {
            "fcff_sensitivity": {
                "base_wacc": 0.13,
                "wacc_range": [0.11, 0.12, 0.13, 0.14, 0.15],
                "matrix": {"0.130": {"0.03": 55000}},
            }
        }
        g = _sensitivity_gate(val)
        assert g.status == "PASS"

    def test_citation_gate_fails_when_unsupported(self):
        ledger = {"summary": {"unsupported": 3, "supported": 5}}
        g = _citation_gate_from_ledger(ledger)
        assert g.status == "FAIL"

    def test_citation_gate_passes_when_all_supported(self):
        ledger = {"summary": {"supported": 10}}
        g = _citation_gate_from_ledger(ledger)
        assert g.status == "PASS"

    def test_human_review_pass_when_approved(self):
        g = _human_review_gate("approved")
        assert g.status == "PASS"

    def test_human_review_fail_when_not_approved(self):
        g = _human_review_gate("pending")
        assert g.status == "FAIL"

    def test_layout_gate_from_audit_pass(self):
        art = _full_artifact()
        audit = run_layout_audit(art)
        g = _layout_gate_from_audit(audit)
        assert g.status == "PASS"  # full artifact has no layout errors

    def test_blocking_gates_listed(self):
        result = self._run()
        assert isinstance(result.blocking_gates, list)
        assert "human_review_gate" in result.blocking_gates

    def test_to_json_serializable(self):
        result = self._run()
        json.loads(result.to_json())

    def test_artifact_render_mode_updated_in_place(self):
        """With all gate inputs valid + approval, artifact is mutated to client_final."""
        art = _full_artifact()
        val = {
            "fcff": {"net_debt_bridge": {"status": "ok"}, "shares_mn": 94.45,
                     "wacc": 0.13, "terminal_growth": 0.03},
            "blend_dcf": {"is_draft_only": False, "target_price_dcf": 30_000.0,
                          "price_fcff": 35_000.0, "price_fcfe": 22_000.0},
            "fcff_sensitivity": {
                "base_wacc": 0.13, "wacc_range": [0.11, 0.12, 0.13, 0.14, 0.15],
                "matrix": {"0.130": {"0.03": 30_000}},
            },
        }
        fc = {
            "debt_schedule": {"is_fcfe_publishable": True, "forecast_method": "zero_debt_policy"},
            "working_capital_schedule": {"ar_days": 90},
            "forecast_years": [],
        }
        # SKIP gates now block export — all optional gates must be supplied
        source = {"untraced_valuation_facts": [], "tier3_only_valuation_facts": []}
        reconciliation = {"material_conflicts": []}
        ledger = {"summary": {"unsupported": 0, "supported": 10}}
        audit = run_layout_audit(art)
        evaluate_export_gate(
            art,
            valuation_artifact=val,
            forecast_artifact=fc,
            source_manifest=source,
            reconciliation_artifact=reconciliation,
            claim_ledger=ledger,
            layout_audit=audit,
            approval_status="approved",
        )
        assert art.render_mode == "client_final"
        assert art.is_final_exportable is True
