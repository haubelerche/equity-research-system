"""Mandatory tests for Phase 3 — source tier coverage gate.

Gate 2 (source provenance) must:
  1. Always run — no silent pass when source_tiers_by_period is None.
  2. Fail when any period has only Tier 3 sources (no Tier 0/1).
  3. Pass/warn when a period has at least one Tier 0 or Tier 1 source.
  4. Distinguish between warn (1 period without Tier 0/1) and fail (2+ periods).

All tests are in-memory — no DB required.
"""
from __future__ import annotations

import pytest

from backend.facts.completeness import check_source_tier_coverage


class TestCheckSourceTierCoverageNoSilentPass:
    """Gate must not silently pass when source_tiers_by_period is None."""

    def test_none_input_does_not_silently_pass(self):
        """Passing None should NOT return status='pass' — the silent pass is removed."""
        result = check_source_tier_coverage(
            ticker="DHG",
            periods_available=["2023FY"],
            source_tiers_by_period=None,
        )
        # With None, all periods have no tiers → should be fail or warn, NOT pass
        assert result["status"] != "pass", (
            "check_source_tier_coverage silently passes with source_tiers_by_period=None. "
            "The silent pass was supposed to be removed in Phase 3."
        )

    def test_empty_dict_treats_all_periods_as_no_source(self):
        result = check_source_tier_coverage(
            ticker="DHG",
            periods_available=["2023FY", "2024FY"],
            source_tiers_by_period={},
        )
        assert result["status"] in ("warn", "fail")
        assert len(result["missing_tier1_periods"]) == 2


class TestTier3OnlyFails:
    def test_single_period_tier3_only_warns(self):
        """One period with only Tier 3 → warn (not fail)."""
        result = check_source_tier_coverage(
            ticker="DHG",
            periods_available=["2023FY"],
            source_tiers_by_period={"2023FY": [3]},
        )
        assert result["status"] == "warn"
        assert "2023FY" in result["tier3_only_periods"]
        assert "2023FY" in result["missing_tier1_periods"]

    def test_two_periods_tier3_only_fails(self):
        """Two or more periods with only Tier 3 → fail."""
        result = check_source_tier_coverage(
            ticker="DHG",
            periods_available=["2022FY", "2023FY"],
            source_tiers_by_period={"2022FY": [3], "2023FY": [3]},
        )
        assert result["status"] == "fail"
        assert len(result["tier3_only_periods"]) == 2

    def test_four_periods_tier3_only_fails(self):
        """DHG with 2022-2025 from vnstock only should fail."""
        result = check_source_tier_coverage(
            ticker="DHG",
            periods_available=["2022FY", "2023FY", "2024FY", "2025FY"],
            source_tiers_by_period={
                "2022FY": [3], "2023FY": [3], "2024FY": [3], "2025FY": [3],
            },
        )
        assert result["status"] == "fail"


class TestTier01Passes:
    def test_all_periods_have_tier0_passes(self):
        result = check_source_tier_coverage(
            ticker="DHG",
            periods_available=["2021FY", "2022FY"],
            source_tiers_by_period={"2021FY": [0], "2022FY": [0]},
        )
        assert result["status"] == "pass"
        assert result["tier3_only_periods"] == []

    def test_all_periods_have_tier1_passes(self):
        result = check_source_tier_coverage(
            ticker="DHG",
            periods_available=["2021FY"],
            source_tiers_by_period={"2021FY": [1]},
        )
        assert result["status"] == "pass"

    def test_mix_tier0_and_tier3_same_period_passes(self):
        """A period with BOTH Tier 0 and Tier 3 sources should pass (Tier 0 is corroborated)."""
        result = check_source_tier_coverage(
            ticker="DHG",
            periods_available=["2023FY"],
            source_tiers_by_period={"2023FY": [0, 3]},
        )
        assert result["status"] == "pass"
        assert "2023FY" not in result["missing_tier1_periods"]

    def test_golden_csv_tier1_makes_period_pass(self):
        """2021FY with golden CSV at Tier 1 should pass even if other periods are Tier 3."""
        result = check_source_tier_coverage(
            ticker="DHG",
            periods_available=["2021FY"],
            source_tiers_by_period={"2021FY": [1, 3]},
        )
        assert result["status"] == "pass"


class TestBlockingReasons:
    def test_tier3_only_adds_blocking_reason(self):
        result = check_source_tier_coverage(
            ticker="DHG",
            periods_available=["2022FY"],
            source_tiers_by_period={"2022FY": [3]},
        )
        assert len(result["blocking_reasons"]) > 0
        assert any("tier3_only" in r for r in result["blocking_reasons"])

    def test_pass_has_no_blocking_reasons(self):
        result = check_source_tier_coverage(
            ticker="DHG",
            periods_available=["2021FY"],
            source_tiers_by_period={"2021FY": [1]},
        )
        assert result["blocking_reasons"] == []
