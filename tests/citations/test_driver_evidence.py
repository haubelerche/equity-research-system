"""Tests for backend/citations/driver_evidence.py — Phase 5."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.citations.driver_evidence import (
    DriverEvidenceBlock,
    build_catalyst_claims,
    render_catalyst_section,
    _build_period_block,
    _render_event_bullet,
)
from backend.citations.event_linker import CatalystEventEntry


# ── helpers ────────────────────────────────────────────────────────────────────

def _event(
    event_id: str = "e1",
    title: str = "DHG BHYT contract renewal",
    causality_level: str = "contextual_event",
    summary: str | None = "Renewal confirmed for FY2023.",
    materiality_hint: str | None = "medium",
    event_type: str = "regulatory",
    ticker: str = "DHG",
) -> CatalystEventEntry:
    return CatalystEventEntry(
        event_id=event_id,
        ticker=ticker,
        event_type=event_type,
        title=title,
        summary=summary,
        occurred_at=datetime.now(UTC).isoformat(),
        materiality_hint=materiality_hint,
        source_url=None,
        source_id="s1",
        causality_level=causality_level,
    )


# ── _render_event_bullet ───────────────────────────────────────────────────────

class TestRenderEventBullet:
    def test_bullet_starts_with_dash(self):
        ev = _event(causality_level="contextual_event")
        result = _render_event_bullet(ev)
        assert result.startswith("- ")

    def test_contextual_event_uses_hedged_wording(self):
        ev = _event(causality_level="contextual_event")
        result = _render_event_bullet(ev)
        assert "diễn ra trong bối cảnh" in result

    def test_potential_driver_uses_possibility_wording(self):
        ev = _event(causality_level="potential_driver")
        result = _render_event_bullet(ev)
        assert "có thể là một yếu tố hỗ trợ" in result

    def test_management_disclosed_uses_attributed_wording(self):
        ev = _event(causality_level="management_disclosed_driver")
        result = _render_event_bullet(ev)
        assert "theo công ty" in result

    def test_validated_driver_uses_evidence_wording(self):
        ev = _event(causality_level="validated_driver")
        result = _render_event_bullet(ev)
        assert "được hỗ trợ bởi" in result

    def test_event_title_is_bold_in_output(self):
        ev = _event(title="GMP factory approved")
        result = _render_event_bullet(ev)
        assert "**GMP factory approved**" in result

    def test_summary_included_when_not_same_as_title(self):
        ev = _event(title="Title", summary="Detailed explanation here.")
        result = _render_event_bullet(ev)
        assert "Detailed explanation here." in result

    def test_summary_omitted_when_same_as_title(self):
        ev = _event(title="Same text", summary="Same text")
        result = _render_event_bullet(ev)
        # The title appears once as bold; summary should not duplicate
        assert result.count("Same text") == 1

    def test_materiality_hint_included(self):
        ev = _event(materiality_hint="high")
        result = _render_event_bullet(ev)
        assert "high" in result

    def test_no_materiality_hint_omits_field(self):
        ev = _event(materiality_hint=None)
        result = _render_event_bullet(ev)
        assert "mức độ" not in result


# ── _build_period_block ────────────────────────────────────────────────────────

class TestBuildPeriodBlock:
    def test_returns_driver_evidence_block(self):
        events = [_event(causality_level="contextual_event")]
        block = _build_period_block("2023FY", events, max_events=5)
        assert isinstance(block, DriverEvidenceBlock)

    def test_period_in_heading(self):
        block = _build_period_block("2023FY", [_event()], max_events=5)
        assert "2023FY" in block.rendered_md

    def test_total_events_count(self):
        events = [_event("e1"), _event("e2")]
        block = _build_period_block("2023FY", events, max_events=5)
        assert block.total_events == 2

    def test_max_events_limits_rendered(self):
        events = [_event(event_id=f"e{i}") for i in range(10)]
        block = _build_period_block("2023FY", events, max_events=3)
        # Block should render at most 3 events
        assert block.total_events == 10  # total = all events
        assert len(block.events_by_level.get("contextual_event", [])) == 3

    def test_validated_driver_rendered_before_contextual(self):
        events = [
            _event("e1", causality_level="contextual_event"),
            _event("e2", causality_level="validated_driver"),
        ]
        block = _build_period_block("2023FY", events, max_events=5)
        idx_validated = block.rendered_md.find("Yếu tố được xác nhận")
        idx_contextual = block.rendered_md.find("Sự kiện bối cảnh")
        assert idx_validated < idx_contextual

    def test_empty_events_returns_empty_block(self):
        block = _build_period_block("2023FY", [], max_events=5)
        assert block.total_events == 0


# ── render_catalyst_section ────────────────────────────────────────────────────

class TestRenderCatalystSection:
    def test_returns_str(self):
        result = render_catalyst_section("DHG", {})
        assert isinstance(result, str)

    def test_empty_periods_returns_placeholder(self):
        result = render_catalyst_section("DHG", {})
        assert "DHG" in result
        assert "ingest_catalyst_sources" in result or "catalyst_events" in result

    def test_no_events_in_any_period_returns_placeholder(self):
        result = render_catalyst_section("DHG", {"2023FY": [], "2022FY": []})
        assert "ingest_catalyst_sources" in result or "catalyst_events" in result

    def test_section_heading_present(self):
        events = {"2023FY": [_event()]}
        result = render_catalyst_section("DHG", events)
        assert "## Yếu tố thúc đẩy" in result

    def test_period_rendered_in_section(self):
        events = {"2023FY": [_event()]}
        result = render_catalyst_section("DHG", events)
        assert "2023FY" in result

    def test_most_recent_period_first(self):
        events = {
            "2021FY": [_event("e1")],
            "2023FY": [_event("e2")],
        }
        result = render_catalyst_section("DHG", events)
        idx_2023 = result.find("2023FY")
        idx_2021 = result.find("2021FY")
        assert idx_2023 < idx_2021

    def test_causal_language_not_in_contextual_bullet(self):
        ev = _event(causality_level="contextual_event")
        result = render_catalyst_section("DHG", {"2023FY": [ev]})
        # Causal keywords must not appear in contextual_event bullets
        causal_keywords = [" do ", " dẫn đến ", " caused by ", " due to ", " driven by "]
        for kw in causal_keywords:
            assert kw.lower() not in result.lower(), f"Causal keyword {kw!r} found in contextual bullet"

    def test_multiple_causality_levels_rendered(self):
        events = {
            "2023FY": [
                _event("e1", causality_level="contextual_event"),
                _event("e2", causality_level="validated_driver"),
            ]
        }
        result = render_catalyst_section("DHG", events)
        assert "Sự kiện bối cảnh" in result
        assert "xác nhận bằng bằng chứng" in result

    def test_max_events_per_period_respected(self):
        many_events = [_event(event_id=f"e{i}") for i in range(10)]
        result = render_catalyst_section("DHG", {"2023FY": many_events}, max_events_per_period=2)
        # At most 2 bullets for the period
        bullet_count = result.count("\n- ")
        assert bullet_count <= 2


# ── build_catalyst_claims ──────────────────────────────────────────────────────

class TestBuildCatalystClaims:
    def test_returns_list(self):
        result = build_catalyst_claims("DHG", {})
        assert isinstance(result, list)
        assert len(result) == 0

    def test_one_event_one_claim(self):
        events = {"2023FY": [_event("e1")]}
        result = build_catalyst_claims("DHG", events)
        assert len(result) == 1

    def test_claim_has_required_keys(self):
        events = {"2023FY": [_event("e1")]}
        claim = build_catalyst_claims("DHG", events)[0]
        for key in ("event_title", "event_type", "source_document_id", "causality_level",
                    "ticker", "ticker_mapping_level", "period", "claim_type"):
            assert key in claim, f"Missing key: {key}"

    def test_source_document_id_is_none(self):
        # fact.catalyst_events lack official_document FK — Gate 6 should flag this
        events = {"2023FY": [_event("e1")]}
        claim = build_catalyst_claims("DHG", events)[0]
        assert claim["source_document_id"] is None

    def test_claim_type_is_catalyst(self):
        events = {"2023FY": [_event("e1")]}
        claim = build_catalyst_claims("DHG", events)[0]
        assert claim["claim_type"] == "catalyst"

    def test_period_matches_input_period(self):
        events = {"2023FY": [_event("e1")], "2022FY": [_event("e2")]}
        claims = build_catalyst_claims("DHG", events)
        periods = {c["period"] for c in claims}
        assert "2023FY" in periods
        assert "2022FY" in periods

    def test_citation_key_format(self):
        events = {"2023FY": [_event("e1")]}
        claim = build_catalyst_claims("DHG", events)[0]
        assert claim["citation_key"].startswith("DHG/2023FY/catalyst.")

    def test_evidence_quote_from_summary(self):
        ev = _event(summary="Evidence text here.")
        claims = build_catalyst_claims("DHG", {"2023FY": [ev]})
        assert claims[0]["evidence_quote"] == "Evidence text here."
