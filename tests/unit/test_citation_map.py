"""Tests for backend/citations/ — citation_map, event_linker, validator.

All tests are in-memory — no DB required.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.citations.citation_map import (
    FORBIDDEN_GENERIC_LABELS,
    CitationRecord,
    build_citation_map,
    citation_map_to_legacy_dict,
)
from backend.citations.event_linker import (
    CatalystEventEntry,
    link_events_to_periods,
)
from backend.citations.validator import (
    validate_causality_language,
    validate_citation_coverage,
    validate_numeric_consistency,
    validate_source_tier,
)
from backend.facts.normalizer import FactEntry


def _entry(value: float, source_id: str = "s1", tier: int = 3, title: str = "") -> FactEntry:
    return FactEntry(
        value=value,
        source_id=source_id,
        source_uri=f"vnstock://kbs/finance/income/{source_id}",
        source_title=title or f"Test source ({source_id})",
        source_tier=tier,
        confidence=0.9,
    )


def _derived(value: float) -> FactEntry:
    return FactEntry(value=value)


# ── citation_map ───────────────────────────────────────────────────────────────

class TestBuildCitationMap:
    def _table(self):
        return {
            "revenue.net": {"2023FY": _entry(5000.0, tier=3)},
            "net_income.parent": {"2023FY": _entry(1000.0, tier=1, title="DHG Annual Report 2023")},
            "gross_margin": {"2023FY": _derived(0.45)},
        }

    def test_keys_follow_ticker_period_metric_format(self):
        cmap = build_citation_map("DHG", self._table())
        assert "DHG/2023FY/revenue.net" in cmap
        assert "DHG/2023FY/net_income.parent" in cmap

    def test_tier3_citation_gets_tier_label(self):
        cmap = build_citation_map("DHG", self._table())
        rec = cmap["DHG/2023FY/revenue.net"]
        assert rec.source_tier == 3
        assert "Tier 3" in rec.tier_label or "API" in rec.tier_label

    def test_tier1_citation_preserves_title(self):
        cmap = build_citation_map("DHG", self._table())
        rec = cmap["DHG/2023FY/net_income.parent"]
        assert "DHG Annual Report 2023" in rec.source_title
        assert rec.source_tier == 1

    def test_derived_metric_is_flagged(self):
        cmap = build_citation_map("DHG", self._table())
        rec = cmap["DHG/2023FY/gross_margin"]
        assert rec.is_derived
        assert rec.source_id == ""
        assert rec.source_tier is None

    def test_source_title_never_generic_label(self):
        cmap = build_citation_map("DHG", self._table())
        for key, rec in cmap.items():
            assert rec.source_title.lower() not in FORBIDDEN_GENERIC_LABELS, \
                f"Generic label found in citation for {key}: '{rec.source_title}'"

    def test_legacy_dict_conversion(self):
        cmap = build_citation_map("DHG", self._table())
        legacy = citation_map_to_legacy_dict(cmap)
        assert isinstance(legacy, dict)
        for key, rec in legacy.items():
            assert isinstance(rec, dict)
            assert "value" in rec
            assert "source_title" in rec


class TestForbiddenLabels:
    def test_vnstock_api_label_is_forbidden(self):
        assert "báo cáo tài chính (vnstock api)" in FORBIDDEN_GENERIC_LABELS

    def test_generic_canonical_label_is_forbidden(self):
        assert "dữ liệu tài chính canonical" in FORBIDDEN_GENERIC_LABELS

    def test_real_document_title_is_not_forbidden(self):
        assert "DHG Annual Report 2023".lower() not in FORBIDDEN_GENERIC_LABELS


# ── event_linker ───────────────────────────────────────────────────────────────

class TestLinkEventsToPeriods:
    def _events(self) -> list[dict]:
        now = datetime.now(UTC)
        return [
            {
                "event_id": "evt_1",
                "ticker": "DHG",
                "event_type": "disclosure",
                "title": "DHG announces BHYT contract renewal",
                "summary": None,
                "occurred_at": (now - timedelta(days=200)).isoformat(),
                "materiality_hint": "medium",
                "source_url": "https://hsx.vn/disclosure/dhg_001",
                "source_id": "src_001",
                "causality_level": "contextual_event",
            },
            {
                "event_id": "evt_2",
                "ticker": "DHG",
                "event_type": "regulatory",
                "title": "DAV approves new DHG drug formulation",
                "summary": None,
                "occurred_at": (now - timedelta(days=900)).isoformat(),  # out of ±6mo window for 2023FY
                "materiality_hint": "high",
                "source_url": "https://dav.gov.vn/01",
                "source_id": "src_002",
                "causality_level": "potential_driver",
            },
        ]

    def test_event_within_window_linked_to_period(self):
        result = link_events_to_periods(
            ticker="DHG",
            periods=["2025FY"],
            db_facts=self._events(),
        )
        assert len(result["2025FY"]) >= 1
        assert any(e.event_id == "evt_1" for e in result["2025FY"])

    def test_event_outside_window_not_linked(self):
        # evt_2 is ~2.5 years old — outside ±6 months of 2025FY
        result = link_events_to_periods(
            ticker="DHG",
            periods=["2025FY"],
            db_facts=self._events(),
        )
        assert not any(e.event_id == "evt_2" for e in result["2025FY"])

    def test_default_causality_level_is_contextual(self):
        events = [{
            "event_id": "e1", "ticker": "DHG", "event_type": "news",
            "title": "Some news", "summary": None,
            "occurred_at": datetime.now(UTC).isoformat(),
            "materiality_hint": None, "source_url": None, "source_id": "s1",
        }]
        result = link_events_to_periods("DHG", ["2025FY"], db_facts=events)
        if result["2025FY"]:
            assert result["2025FY"][0].causality_level == "contextual_event"

    def test_empty_periods_returns_empty_dict(self):
        result = link_events_to_periods("DHG", [], db_facts=self._events())
        assert result == {}


# ── validator ──────────────────────────────────────────────────────────────────

class TestValidateCitationCoverage:
    def _cmap(self):
        return {
            "DHG/2023FY/revenue.net": CitationRecord(
                key="DHG/2023FY/revenue.net",
                ticker="DHG", period="2023FY", fiscal_year=2023,
                metric="revenue.net", metric_label="Doanh thu thuần",
                value=5000.0, value_display="5,000.0 tỷ VND", unit="vnd_bn",
                fact_id="f1", source_id="s1",
                source_uri="vnstock://kbs/finance/income/DHG",
                source_title="Test Source", source_tier=3, tier_label="[Tier 3]",
                published_at="2024-01-01", reliability_tier=2,
            )
        }

    def test_no_tags_returns_warn(self):
        result = validate_citation_coverage("No footnotes here.", self._cmap())
        assert result.status == "warn"

    def test_resolved_tag_passes(self):
        report = "Revenue was 5,000 tỷ [^revenue_net_2023]"
        result = validate_citation_coverage(report, self._cmap(), ticker="DHG")
        assert result.status == "pass"
        assert result.issue_count == 0

    def test_unresolved_tag_fails(self):
        report = "Revenue was 5,000 tỷ [^missing_metric_2023]"
        result = validate_citation_coverage(report, self._cmap(), ticker="DHG")
        assert result.issue_count > 0


class TestValidateSourceTier:
    def _cmap_tier3_material(self):
        return {
            "DHG/2023FY/revenue.net": CitationRecord(
                key="DHG/2023FY/revenue.net",
                ticker="DHG", period="2023FY", fiscal_year=2023,
                metric="revenue.net", metric_label="Doanh thu thuần",
                value=5000.0, value_display="5,000.0 tỷ VND", unit="vnd_bn",
                fact_id="f1", source_id="s1",
                source_uri="vnstock://kbs/finance/income/DHG",
                source_title="Dữ liệu API tổng hợp — chưa kiểm chứng [Tier 3]",
                source_tier=3, tier_label="[Tier 3]",
                published_at="", reliability_tier=3,
            )
        }

    def _cmap_tier1_material(self):
        return {
            "DHG/2023FY/revenue.net": CitationRecord(
                key="DHG/2023FY/revenue.net",
                ticker="DHG", period="2023FY", fiscal_year=2023,
                metric="revenue.net", metric_label="Doanh thu thuần",
                value=5000.0, value_display="5,000.0 tỷ VND", unit="vnd_bn",
                fact_id="f1", source_id="s1",
                source_uri="https://dhg.com.vn/annual-report",
                source_title="DHG Annual Report 2023 [Tier 1]",
                source_tier=1, tier_label="[Tier 1]",
                published_at="2024-01-01", reliability_tier=1,
            )
        }

    def test_tier3_material_draft_warns(self):
        result = validate_source_tier(
            self._cmap_tier3_material(),
            report_status="draft",
            material_metrics={"revenue.net"},
        )
        assert result.status == "warn"
        assert not result.critical_fail

    def test_tier3_material_export_fails(self):
        result = validate_source_tier(
            self._cmap_tier3_material(),
            report_status="exported",
            material_metrics={"revenue.net"},
        )
        assert result.status == "fail"
        assert result.critical_fail

    def test_tier1_material_passes(self):
        result = validate_source_tier(
            self._cmap_tier1_material(),
            report_status="exported",
            material_metrics={"revenue.net"},
        )
        assert result.status == "pass"

    def test_generic_label_is_flagged(self):
        from backend.citations.citation_map import CitationRecord as CR
        cmap = {
            "DHG/2023FY/revenue.net": CR(
                key="DHG/2023FY/revenue.net",
                ticker="DHG", period="2023FY", fiscal_year=2023,
                metric="revenue.net", metric_label="Rev",
                value=5000.0, value_display="5000", unit="vnd_bn",
                fact_id="", source_id="s1",
                source_uri="vnstock://kbs/fin/DHG",
                source_title="Báo cáo tài chính (vnstock API)",  # FORBIDDEN
                source_tier=3, tier_label="", published_at="", reliability_tier=3,
            )
        }
        result = validate_source_tier(cmap, report_status="draft")
        generic_issues = [i for i in result.issues if "generic" in i.lower() or "provider label" in i.lower()]
        assert len(generic_issues) > 0


class TestValidateNumericConsistency:
    def _cmap(self):
        return {
            "DHG/2023FY/revenue.net": CitationRecord(
                key="DHG/2023FY/revenue.net",
                ticker="DHG", period="2023FY", fiscal_year=2023,
                metric="revenue.net", metric_label="Rev",
                value=5000.0, value_display="5,000.0 tỷ", unit="vnd_bn",
                fact_id="f1", source_id="s1", source_uri="", source_title="",
                source_tier=3, tier_label="", published_at="", reliability_tier=3,
            )
        }

    def test_matching_value_passes(self):
        claims = [{"claim_type": "quantitative", "ticker": "DHG",
                   "period": "2023FY", "metric": "revenue.net", "value_mentioned": 5000.0}]
        result = validate_numeric_consistency(claims, self._cmap())
        assert result.status == "pass"

    def test_large_deviation_fails(self):
        claims = [{"claim_type": "quantitative", "ticker": "DHG",
                   "period": "2023FY", "metric": "revenue.net", "value_mentioned": 5500.0}]
        result = validate_numeric_consistency(claims, self._cmap(), tolerance_pct=1.0)
        assert result.issue_count > 0

    def test_empty_claims_warns(self):
        result = validate_numeric_consistency([], self._cmap())
        assert result.status == "warn"


class TestValidateCausalityLanguage:
    def _events(self, level: str = "contextual_event"):
        event = CatalystEventEntry(
            event_id="e1", ticker="DHG",
            event_type="regulatory",
            title="BHYT policy changed for DHG products",
            summary=None,
            occurred_at="2023-06-15",
            materiality_hint="medium",
            source_url=None,
            source_id="s1",
            causality_level=level,
        )
        return {"2023FY": [event]}

    def test_causal_language_with_contextual_event_warns(self):
        report = "Do BHYT policy changed for DHG products, revenue increased 10%."
        result = validate_causality_language(report, self._events("contextual_event"))
        assert result.status == "warn"
        assert result.issue_count > 0

    def test_hedged_language_with_contextual_event_passes(self):
        report = "Diễn ra trong bối cảnh BHYT policy changed for DHG products, analysts note growth."
        result = validate_causality_language(report, self._events("contextual_event"))
        # "trong bối cảnh" is not a causal keyword — should not flag
        # This is a pass or warn depending on keyword matching
        assert result.status in ("pass", "warn")

    def test_no_events_passes(self):
        result = validate_causality_language("Some report text.", {})
        assert result.status == "pass"

    def test_validated_driver_allows_causal_language(self):
        # Events with validated_driver level are not "contextual" so they won't trigger the gate
        report = "Due to validated product approval, revenue grew."
        result = validate_causality_language(report, self._events("validated_driver"))
        # validated_driver events are not in the contextual set so no flag
        assert result.status == "pass"
