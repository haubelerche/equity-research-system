"""Unit tests for backend/facts/completeness.py.

Tests: build_fy_validation_report, score_completeness, score_freshness.
No DB required — all in-memory.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.facts.completeness import (
    CORE_FY_KEYS,
    MIN_FY_PERIODS,
    build_fy_validation_report,
    score_completeness,
    score_freshness,
)


def _make_complete_table(periods: list[str]) -> dict:
    """Create a fact table with all CORE_FY_KEYS present for all given periods."""
    from backend.facts.normalizer import FactEntry
    def e(v):
        return FactEntry(value=v, source_id="test_src", source_tier=1)
    table: dict = {}
    for key in CORE_FY_KEYS:
        table[key] = {p: e(1000.0) for p in periods}
    # Also add some extra keys
    table["gross_profit.total"] = {p: e(500.0) for p in periods}
    return table


def _make_vstatus_table(periods: list[str], status: str = "accepted") -> dict:
    """Create a validation status table with given status for all CORE_FY_KEYS."""
    return {key: {p: status for p in periods} for key in CORE_FY_KEYS}


def _make_raw_facts(periods: list[str], days_ago: int = 5) -> list[dict]:
    ingested = datetime.now(UTC) - timedelta(days=days_ago)
    return [
        {"line_item_code": "revenue.net", "fiscal_year": int(p[:4]),
         "fiscal_period": "FY", "value": 1000.0,
         "source_tier": 1,   # Tier 1 so tier coverage gate passes in these baseline tests
         "ingested_at": ingested}
        for p in periods
    ]


class TestBuildFyValidationReport:
    _periods = ["2021FY", "2022FY", "2023FY"]
    _required = ["2021FY", "2022FY", "2023FY", "2024FY", "2025FY"]

    def _run(self, table=None, raw_facts=None, vstatus_table=None,
             periods_available=None, periods_missing=None):
        if table is None:
            table = _make_complete_table(self._periods)
        if raw_facts is None:
            raw_facts = _make_raw_facts(self._periods)
        if periods_available is None:
            periods_available = self._periods
        if periods_missing is None:
            periods_missing = [p for p in self._required if p not in periods_available]
        if vstatus_table is None:
            vstatus_table = _make_vstatus_table(self._periods)

        return build_fy_validation_report(
            ticker="DHG",
            table=table,
            raw_facts=raw_facts,
            required_periods=self._required,
            periods_available=periods_available,
            periods_missing=periods_missing,
            forbidden_periods=[],
            generated_at=datetime.now(UTC),
            validation_status_table=vstatus_table,
        )

    def test_all_gates_pass_when_complete(self):
        report = self._run()
        assert report["coverage_gate"] == "pass"
        assert report["core_keys_gate"] == "pass"
        assert report["source_validation_gate"] == "pass"
        assert report["valuation_gate"] == "pass"
        assert report["valuation_ready"] is True

    def test_coverage_gate_fails_below_minimum_periods(self):
        two_periods = ["2022FY", "2023FY"]
        report = self._run(
            table=_make_complete_table(two_periods),
            raw_facts=_make_raw_facts(two_periods),
            vstatus_table=_make_vstatus_table(two_periods),
            periods_available=two_periods,
        )
        assert report["coverage_gate"] == "fail"
        assert report["valuation_ready"] is False

    def test_core_keys_gate_fails_when_key_missing(self):
        periods = ["2021FY", "2022FY", "2023FY"]
        table = _make_complete_table(periods)
        del table["revenue.net"]  # Remove a CORE_FY_KEY entirely
        report = self._run(table=table)
        assert report["core_keys_gate"] == "fail"
        assert report["valuation_ready"] is False

    def test_source_validation_gate_fails_when_not_accepted(self):
        vstatus_table = _make_vstatus_table(self._periods, status="needs_review")
        report = self._run(vstatus_table=vstatus_table)
        assert report["source_validation_gate"] == "fail"
        assert report["valuation_ready"] is False

    def test_no_vstatus_table_fails_source_gate(self):
        report = build_fy_validation_report(
            ticker="DHG",
            table=_make_complete_table(self._periods),
            raw_facts=_make_raw_facts(self._periods),
            required_periods=self._required,
            periods_available=self._periods,
            periods_missing=["2024FY", "2025FY"],
            forbidden_periods=[],
            generated_at=datetime.now(UTC),
            validation_status_table=None,  # not provided
        )
        assert report["source_validation_gate"] == "fail"

    def test_annual_reports_collected_count(self):
        report = self._run()
        assert report["annual_reports_collected"] == 3

    def test_blocking_reasons_populated_on_fail(self):
        two_periods = ["2022FY", "2023FY"]
        report = self._run(
            table=_make_complete_table(two_periods),
            raw_facts=_make_raw_facts(two_periods),
            vstatus_table=_make_vstatus_table(two_periods),
            periods_available=two_periods,
        )
        assert len(report["blocking_reasons"]) > 0

    def test_freshness_data_age_computed(self):
        report = self._run(raw_facts=_make_raw_facts(self._periods, days_ago=10))
        assert report["data_age_days"] is not None
        assert 9 <= report["data_age_days"] <= 11  # rough window for test timing

    def test_run_status_ok_when_all_pass(self):
        report = self._run()
        assert report["run_status"] == "ok"

    def test_run_status_needs_fallback_when_coverage_fails(self):
        two_periods = ["2022FY", "2023FY"]
        report = self._run(
            table=_make_complete_table(two_periods),
            raw_facts=_make_raw_facts(two_periods),
            vstatus_table=_make_vstatus_table(two_periods),
            periods_available=two_periods,
        )
        assert report["run_status"] == "needs_fallback"


class TestScoreCompleteness:
    def test_all_required_present(self):
        from backend.facts.completeness import REQUIRED_KEYS
        periods = ["2022FY", "2023FY"]
        table = {key: {p: 1.0 for p in periods} for key in REQUIRED_KEYS}
        result = score_completeness(table=table, periods=periods)
        assert result["completeness_score"] == pytest.approx(1.0)
        assert result["required_missing"] == []

    def test_missing_keys_penalize_score(self):
        from backend.facts.completeness import REQUIRED_KEYS
        periods = ["2022FY", "2023FY"]
        # Only include half the required keys
        table = {key: {p: 1.0 for p in periods} for key in REQUIRED_KEYS[:5]}
        result = score_completeness(table=table, periods=periods)
        assert result["completeness_score"] < 1.0
        assert len(result["required_missing"]) > 0

    def test_empty_table(self):
        result = score_completeness(table={}, periods=["2023FY"])
        assert result["completeness_score"] == pytest.approx(0.0)

    def test_per_period_scores_computed(self):
        from backend.facts.completeness import REQUIRED_KEYS
        periods = ["2022FY", "2023FY"]
        # All keys present for 2023FY, none for 2022FY
        table = {key: {"2023FY": 1.0} for key in REQUIRED_KEYS}
        result = score_completeness(table=table, periods=periods)
        assert result["per_period"]["2023FY"] == pytest.approx(1.0)
        assert result["per_period"]["2022FY"] == pytest.approx(0.0)


class TestScoreFreshness:
    def test_current_data_scores_high(self):
        recent = [datetime.now(UTC) - timedelta(days=10)]
        result = score_freshness(periods=["2025FY"], ingested_at_values=recent)
        assert result["freshness_score"] >= 1.0
        assert result["freshness_status"] == "current"

    def test_stale_ingestion_when_age_exceeds_threshold(self):
        from backend.facts.completeness import FRESHNESS_THRESHOLD_DAYS
        old_ingested = [datetime.now(UTC) - timedelta(days=FRESHNESS_THRESHOLD_DAYS + 10)]
        result = score_freshness(periods=["2025FY"], ingested_at_values=old_ingested)
        assert result["freshness_status"] == "stale_ingestion"
        assert result["freshness_score"] <= 0.5

    def test_no_ingested_at_values(self):
        result = score_freshness(periods=["2023FY"], ingested_at_values=[])
        assert result["data_age_days"] is None

    def test_no_periods(self):
        result = score_freshness(periods=[], ingested_at_values=[])
        assert result["freshness_status"] == "no_data"
        assert result["freshness_score"] == pytest.approx(0.0)
