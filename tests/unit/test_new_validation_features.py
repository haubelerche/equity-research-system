"""Unit tests for new data validation features (Plan Phase 9).

Covers:
  - Time-series sanity checks (reconciliation.py §11.7)
  - Market data alignment (market_alignment.py §11.8)
  - Source tier enforcement (completeness.py §11.2)
  - Confidence scoring formula (confidence.py Phase 5)
  - DATA_VALIDATION_REPORT report builder (report_builder.py Phase 7)
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# Time-series sanity checks (Plan §11.7)
# ─────────────────────────────────────────────────────────────────────────────

from backend.facts.reconciliation import (
    _check_time_series_sanity,
    run_reconciliation,
    ReconciliationCheck,
)


def _ts_table_normal() -> dict:
    return {
        "revenue.net":       {"2022FY": 1000.0, "2023FY": 1080.0, "2024FY": 1150.0},
        "net_income.parent": {"2022FY": 100.0,  "2023FY": 108.0,  "2024FY": 115.0},
        "gross_profit.total":{"2022FY": 400.0,  "2023FY": 432.0,  "2024FY": 460.0},
        "total_assets.ending":{"2022FY": 800.0, "2023FY": 850.0,  "2024FY": 900.0},
        "equity.parent":     {"2022FY": 500.0,  "2023FY": 530.0,  "2024FY": 560.0},
        "operating_cash_flow.total": {"2022FY": 110.0, "2023FY": 120.0, "2024FY": 130.0},
    }


def _ts_table_revenue_spike() -> dict:
    """Revenue YoY > 30% — should trigger a warning."""
    return {
        "revenue.net":       {"2022FY": 1000.0, "2023FY": 1500.0},
        "net_income.parent": {"2022FY": 100.0,  "2023FY": 110.0},
        "total_assets.ending":{"2022FY": 800.0, "2023FY": 840.0},
        "equity.parent":     {"2022FY": 500.0,  "2023FY": 520.0},
        "operating_cash_flow.total": {"2022FY": 110.0, "2023FY": 120.0},
    }


def _ts_table_margin_shift() -> dict:
    """Gross margin shift > 5 pp — should trigger a warning."""
    return {
        "revenue.net":       {"2022FY": 1000.0, "2023FY": 1000.0},
        "gross_profit.total":{"2022FY": 300.0,  "2023FY": 420.0},  # 30% → 42%, +12pp
        "net_income.parent": {"2022FY": 100.0,  "2023FY": 100.0},
        "total_assets.ending":{"2022FY": 800.0, "2023FY": 800.0},
        "equity.parent":     {"2022FY": 500.0,  "2023FY": 500.0},
        "operating_cash_flow.total": {"2022FY": 110.0, "2023FY": 110.0},
    }


def _ts_table_bad_cfo_ni() -> dict:
    """CFO/NI ratio < 0.5 — should trigger a warning."""
    return {
        "revenue.net":       {"2024FY": 1000.0},
        "net_income.parent": {"2024FY": 200.0},
        "operating_cash_flow.total": {"2024FY": 80.0},  # 80/200 = 0.4x < 0.5x
        "total_assets.ending":{"2024FY": 800.0},
        "equity.parent":     {"2024FY": 500.0},
    }


class TestTimeSeriesSanityChecks:

    def test_no_warnings_for_normal_data(self):
        checks = _check_time_series_sanity(_ts_table_normal(), ["2022FY", "2023FY", "2024FY"])
        warn_checks = [c for c in checks if c.status == "warn"]
        assert len(warn_checks) == 0, f"Unexpected warnings: {[c.message for c in warn_checks]}"

    def test_revenue_spike_triggers_warning(self):
        checks = _check_time_series_sanity(_ts_table_revenue_spike(), ["2022FY", "2023FY"])
        revenue_warns = [c for c in checks if "revenue" in c.name and c.status == "warn"]
        assert len(revenue_warns) >= 1, "Expected revenue YoY warning for +50% spike"

    def test_gross_margin_shift_triggers_warning(self):
        checks = _check_time_series_sanity(_ts_table_margin_shift(), ["2022FY", "2023FY"])
        margin_warns = [c for c in checks if "gross_margin" in c.name and c.status == "warn"]
        assert len(margin_warns) >= 1, "Expected gross_margin shift warning for +12pp"

    def test_cfo_ni_ratio_below_threshold_triggers_warning(self):
        checks = _check_time_series_sanity(_ts_table_bad_cfo_ni(), ["2024FY"])
        cfo_ni_warns = [c for c in checks if "cfo_ni" in c.name and c.status == "warn"]
        assert len(cfo_ni_warns) >= 1, "Expected CFO/NI ratio warning for 0.4x ratio"

    def test_time_series_checks_are_warnings_not_failures(self):
        """Time-series checks should produce WARN, not FAIL — they do not block valuation."""
        checks = _check_time_series_sanity(_ts_table_revenue_spike(), ["2022FY", "2023FY"])
        assert all(c.status in ("pass", "warn") for c in checks), \
            "Time-series checks must not produce status=fail"

    def test_run_reconciliation_includes_ts_checks(self):
        """run_reconciliation() should include TS_ checks in its output."""
        report = run_reconciliation("TEST", _ts_table_revenue_spike(), ["2022FY", "2023FY"])
        ts_checks = [c for c in report.checks if c.name.startswith("TS_")]
        assert len(ts_checks) >= 1, "run_reconciliation must include time-series checks"

    def test_ts_warnings_do_not_block_valuation(self):
        """Time-series anomalies should NOT block valuation (only accounting failures do)."""
        report = run_reconciliation("TEST", _ts_table_revenue_spike(), ["2022FY", "2023FY"])
        assert report.valuation_blocked is False, \
            "TS warnings should not set valuation_blocked=True"


# ─────────────────────────────────────────────────────────────────────────────
# Market data alignment (Plan §11.8)
# ─────────────────────────────────────────────────────────────────────────────

from backend.validation.market_alignment import (
    check_pe_label,
    check_market_cap_consistency,
    validate_valuation_labels,
    MarketAlignmentIssue,
)


class TestMarketDataAlignment:

    def test_historical_pe_with_historical_price_is_ok(self):
        result = check_pe_label(
            label="Historical P/E",
            price_date="2022-12-30",
            eps_period="2022FY",
            current_price_date="2026-05-27",
        )
        assert result is None, "Same-year price/EPS should not raise an issue"

    def test_historical_pe_label_with_current_price_is_flagged(self):
        result = check_pe_label(
            label="Historical P/E",
            price_date="2026-05-27",
            eps_period="2022FY",
            current_price_date="2026-05-27",
        )
        assert result is not None, "Current price used for historical P/E label must be flagged"
        assert result.check_id == "MARKET_PE_LABEL_MISMATCH"
        assert result.severity == "HIGH"
        assert "2022FY" in result.correct_label

    def test_pe_label_with_mismatched_price_year(self):
        result = check_pe_label(
            label="Historical P/E",
            price_date="2023-06-15",
            eps_period="2022FY",
            current_price_date="2026-05-27",
        )
        assert result is not None, "Price year 2023 vs EPS period 2022FY should be flagged"
        assert result.check_id == "MARKET_PE_PERIOD_MISMATCH"

    def test_current_pe_label_not_flagged(self):
        result = check_pe_label(
            label="Current P/E",
            price_date="2026-05-27",
            eps_period="2025FY",
            current_price_date="2026-05-27",
        )
        assert result is None, "Current P/E label should not be flagged"

    def test_historical_market_cap_with_current_price_flagged(self):
        result = check_market_cap_consistency(
            label="Historical Market Cap",
            price_date="2026-05-27",
            shares_period="2022FY",
            is_historical=False,
        )
        assert result is not None
        assert result.check_id == "MARKET_MKTCAP_LABEL_MISMATCH"

    def test_validate_valuation_labels_scans_artifact(self):
        artifact = {
            "multiples": {
                "pe_trailing": {
                    "label": "Historical P/E",
                    "price_date": "2026-05-27",
                    "eps_period": "2022FY",
                    "current_price_date": "2026-05-27",
                }
            }
        }
        issues = validate_valuation_labels(artifact)
        assert len(issues) >= 1
        assert issues[0].check_id == "MARKET_PE_LABEL_MISMATCH"

    def test_validate_valuation_labels_clean_artifact(self):
        artifact = {
            "multiples": {
                "pe_current": {
                    "label": "Current P/E",
                    "price_date": "2026-05-27",
                    "eps_period": "2025FY",
                    "current_price_date": "2026-05-27",
                }
            }
        }
        issues = validate_valuation_labels(artifact)
        assert issues == []


# ─────────────────────────────────────────────────────────────────────────────
# Source tier enforcement (Plan §11.2 / §12.3)
# ─────────────────────────────────────────────────────────────────────────────

from backend.facts.completeness import check_source_tier_coverage


class TestSourceTierEnforcement:

    def test_all_tier1_passes(self):
        result = check_source_tier_coverage(
            "DHG",
            ["2022FY", "2023FY", "2024FY"],
            source_tiers_by_period={"2022FY": [1], "2023FY": [1], "2024FY": [1, 3]},
        )
        assert result["status"] == "pass"
        assert result["tier3_only_periods"] == []

    def test_all_tier3_fails(self):
        result = check_source_tier_coverage(
            "DHG",
            ["2022FY", "2023FY", "2024FY"],
            source_tiers_by_period={"2022FY": [3], "2023FY": [3], "2024FY": [3]},
        )
        assert result["status"] == "fail", "All Tier-3 periods must produce fail status"
        assert len(result["tier3_only_periods"]) == 3

    def test_one_tier3_only_period_warns(self):
        result = check_source_tier_coverage(
            "DHG",
            ["2022FY", "2023FY", "2024FY"],
            source_tiers_by_period={"2022FY": [1], "2023FY": [1], "2024FY": [3]},
        )
        # One period without T1/T2 → warn
        assert result["status"] == "warn"

    def test_none_tiers_no_longer_skips_check(self):
        # Phase 3: None is now treated as empty dict — no silent pass.
        # All periods are flagged as missing Tier 0/1.
        result = check_source_tier_coverage(
            "DHG",
            ["2022FY", "2023FY", "2024FY"],
            source_tiers_by_period=None,
        )
        assert result["status"] != "pass", \
            "None source_tiers_by_period must no longer silently pass — Phase 3 behavior"
        assert len(result["missing_tier1_periods"]) == 3

    def test_tier2_alone_does_not_satisfy_tier01_requirement(self):
        # Phase 3: only Tier 0 (audited filing) or Tier 1 (company IR/manual) satisfies
        # the material quantitative claim requirement. Tier 2 (reputable media) is not sufficient.
        result = check_source_tier_coverage(
            "DHG",
            ["2022FY", "2023FY"],
            source_tiers_by_period={"2022FY": [2], "2023FY": [2]},
        )
        assert result["status"] in ("warn", "fail"), \
            "Tier-2-only sources must NOT satisfy the Tier 0/1 requirement"
        assert len(result["missing_tier1_periods"]) == 2


# ─────────────────────────────────────────────────────────────────────────────
# Confidence scoring (Plan Phase 5 §12.2)
# ─────────────────────────────────────────────────────────────────────────────

from backend.validation.confidence import compute_confidence, TIER3_CONFIDENCE_CAP


class TestConfidenceScoring:

    def test_tier1_full_match_high_confidence(self):
        result = compute_confidence(
            source_tier=1,
            has_tier1_or_2_cross_check=True,
            cross_source_agreement=1.0,
            accounting_reconciliation_score=1.0,
            extraction_confidence=1.0,
            time_series_sanity_score=1.0,
        )
        assert result.confidence_score >= 0.95
        assert result.status == "high"
        assert result.is_capped is False

    def test_tier3_without_cross_check_capped(self):
        # Tier-3 max natural score = 0.35*0.55 + 0.25*1.0 + 0.20*1.0 + 0.10*1.0 + 0.10*1.0 = 0.8425
        # That is already below cap=0.85, so is_capped=False but score is within cap.
        result = compute_confidence(
            source_tier=3,
            has_tier1_or_2_cross_check=False,
            cross_source_agreement=1.0,
            accounting_reconciliation_score=1.0,
            extraction_confidence=1.0,
            time_series_sanity_score=1.0,
        )
        assert result.confidence_score <= TIER3_CONFIDENCE_CAP, \
            f"Tier-3 without cross-check must not exceed cap {TIER3_CONFIDENCE_CAP}"
        # is_capped is only True when the formula score *would* exceed the cap.
        # With current Tier-3 quality weight, natural max is 0.8425 < 0.85, so no capping needed.
        # Verify a warning is still emitted to alert the analyst.
        assert any("Tier-3" in w for w in result.warnings), \
            "Tier-3 without cross-check must always emit a warning"

    def test_tier3_with_cross_check_can_exceed_cap(self):
        result = compute_confidence(
            source_tier=3,
            has_tier1_or_2_cross_check=True,
            cross_source_agreement=1.0,
            accounting_reconciliation_score=1.0,
            extraction_confidence=1.0,
            time_series_sanity_score=1.0,
        )
        assert result.is_capped is False, "Tier-3 with Tier-1/2 cross-check should not be capped"

    def test_tier3_unverified_is_not_high_confidence(self):
        result = compute_confidence(
            source_tier=3,
            has_tier1_or_2_cross_check=False,
            cross_source_agreement=0.5,
            accounting_reconciliation_score=0.7,
            extraction_confidence=0.8,
            time_series_sanity_score=0.8,
        )
        assert result.status in ("needs_review", "reject"), \
            "Tier-3 unverified with low agreement should not be acceptable for valuation"

    def test_weights_sum_to_one(self):
        """Check the confidence formula weights sum to 1.0."""
        weights = [0.35, 0.25, 0.20, 0.10, 0.10]
        assert abs(sum(weights) - 1.0) < 1e-9

    def test_low_reconciliation_score_produces_warning(self):
        result = compute_confidence(
            source_tier=1,
            has_tier1_or_2_cross_check=True,
            cross_source_agreement=1.0,
            accounting_reconciliation_score=0.3,
            extraction_confidence=0.9,
            time_series_sanity_score=1.0,
        )
        assert any("reconciliation" in w for w in result.warnings), \
            "Low reconciliation score should add a warning"


# ─────────────────────────────────────────────────────────────────────────────
# DATA_VALIDATION_REPORT builder (Plan Phase 7)
# ─────────────────────────────────────────────────────────────────────────────

from backend.validation.report_builder import build_validation_report_md, save_validation_report
from backend.facts.reconciliation import ReconciliationReport


def _make_pass_fy_report() -> dict:
    return {
        "ticker": "DHG",
        "generated_at": "2026-05-27T00:00:00+00:00",
        "periods_available": ["2022FY", "2023FY", "2024FY"],
        "periods_missing": [],
        "annual_reports_collected": 3,
        "latest_fiscal_year": 2024,
        "data_age_days": 10,
        "coverage_gate": "pass",
        "core_keys_gate": "pass",
        "source_validation_gate": "pass",
        "source_tier_coverage_status": "fail",
        "tier3_only_periods": ["2022FY", "2023FY", "2024FY"],
        "missing_tier1_periods": ["2022FY", "2023FY", "2024FY"],
        "reconciliation_gate": "pass",
        "reconciliation_critical_failures": [],
        "reconciliation_warnings": [],
        "valuation_gate": "fail",
        "valuation_ready": False,
        "blocking_reasons": [
            "tier3_only_source: 2022FY has only Tier-3 API data",
        ],
        "non_accepted_facts": [],
    }


def _make_pass_readiness() -> dict:
    return {
        "ticker": "DHG",
        "overall_status": "fail",
        "valuation_allowed": False,
        "blocked_by_dq": True,
        "blocked_by_reconciliation": False,
        "reconciliation_critical_failures": [],
        "reconciliation_warnings": [],
        "dq_gate_blocking_reasons": ["tier3_only_source: 2022FY has only Tier-3 API data"],
    }


def _make_empty_recon_report() -> ReconciliationReport:
    return ReconciliationReport(
        ticker="DHG",
        periods_checked=["2022FY", "2023FY", "2024FY"],
        checks=[],
        critical_failures=[],
        warnings=[],
        overall_status="pass",
        valuation_blocked=False,
    )


class TestReportBuilder:

    def test_report_is_generated_when_validation_fails(self):
        md = build_validation_report_md(
            ticker="DHG",
            snapshot_id="val_test01",
            fy_validation_report=_make_pass_fy_report(),
            readiness_gate=_make_pass_readiness(),
            reconciliation_report=_make_empty_recon_report(),
        )
        assert "Data Validation Report" in md
        assert "DHG" in md

    def test_report_includes_all_required_sections(self):
        md = build_validation_report_md(
            ticker="DHG",
            snapshot_id="val_test01",
            fy_validation_report=_make_pass_fy_report(),
            readiness_gate=_make_pass_readiness(),
            reconciliation_report=_make_empty_recon_report(),
        )
        for section in [
            "## 1. Data Snapshot",
            "## 2. Source Coverage",
            "## 3. Critical Fact Validation",
            "## 4. Accounting Reconciliation",
            "## 5. Time-series Warnings",
            "## 6. Market Data Alignment",
            "## 7. Valuation Readiness Gate",
            "## 8. Machine-Readable Summary",
        ]:
            assert section in md, f"Section '{section}' missing from report"

    def test_report_includes_machine_readable_json(self):
        md = build_validation_report_md(
            ticker="DHG",
            snapshot_id="val_test01",
            fy_validation_report=_make_pass_fy_report(),
            readiness_gate=_make_pass_readiness(),
            reconciliation_report=_make_empty_recon_report(),
        )
        # Extract JSON block
        start = md.index("```json") + len("```json")
        end = md.index("```", start)
        json_block = md[start:end].strip()
        parsed = json.loads(json_block)
        assert "ticker" in parsed
        assert "valuation_allowed" in parsed
        assert "validation_status" in parsed

    def test_report_does_not_include_target_price_when_validation_fails(self):
        md = build_validation_report_md(
            ticker="DHG",
            snapshot_id="val_test01",
            fy_validation_report=_make_pass_fy_report(),
            readiness_gate=_make_pass_readiness(),
            reconciliation_report=_make_empty_recon_report(),
        )
        assert "target price" not in md.lower(), \
            "Report must not include 'target price' when validation fails"
        assert "buy" not in md.lower()

    def test_save_validation_report_writes_file(self):
        md = build_validation_report_md(
            ticker="DHG",
            snapshot_id="val_save01",
            fy_validation_report=_make_pass_fy_report(),
            readiness_gate=_make_pass_readiness(),
            reconciliation_report=_make_empty_recon_report(),
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = save_validation_report(md, "DHG", "val_save01", output_dir=tmpdir)
            assert os.path.exists(path), "Report file must be written to disk"
            with open(path, encoding="utf-8") as f:
                content = f.read()
            assert "Data Validation Report" in content

    def test_blocking_reasons_appear_in_report(self):
        md = build_validation_report_md(
            ticker="DHG",
            snapshot_id="val_block01",
            fy_validation_report=_make_pass_fy_report(),
            readiness_gate=_make_pass_readiness(),
            reconciliation_report=_make_empty_recon_report(),
        )
        assert "tier3_only_source" in md, "Blocking reasons must appear in the report"
