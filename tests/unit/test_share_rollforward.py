"""Tests for backend.analytics.share_rollforward."""
from __future__ import annotations

import json
import pytest

from backend.analytics.share_rollforward import (
    build_share_rollforward,
    CorporateAction,
    ShareRollForward,
)

_PERIODS = ["2022FY", "2023FY", "2024FY", "2025FY"]
_LABELS  = ["2026F", "2027F", "2028F"]


def _ft_with_shares(shares_abs: float = 94_450_000.0) -> dict:
    """Fact table with ending shares stored as absolute count (canonical format)."""
    return {
        "shares_outstanding.ending": {
            p: {"value": shares_abs} for p in _PERIODS
        }
    }


class TestBaseShares:
    def test_reads_shares_from_fact_table(self):
        sr = build_share_rollforward(
            ticker="DBD", fact_table=_ft_with_shares(94_450_000),
            fy_periods=_PERIODS, forecast_labels=_LABELS,
        )
        assert sr.base_shares_mn is not None
        assert abs(sr.base_shares_mn - 94.45) < 0.01

    def test_override_takes_precedence(self):
        sr = build_share_rollforward(
            ticker="DBD", fact_table=_ft_with_shares(94_450_000),
            fy_periods=_PERIODS, forecast_labels=_LABELS,
            base_shares_override_mn=100.0,
        )
        assert abs(sr.base_shares_mn - 100.0) < 0.001

    def test_missing_shares_emits_warning(self):
        sr = build_share_rollforward(
            ticker="DBD", fact_table={},
            fy_periods=_PERIODS, forecast_labels=_LABELS,
        )
        assert sr.base_shares_mn is None
        assert any("shares" in w.lower() for w in sr.warnings)

    def test_missing_shares_sets_diluted_none(self):
        sr = build_share_rollforward(
            ticker="DBD", fact_table={},
            fy_periods=_PERIODS, forecast_labels=_LABELS,
        )
        schedule = sr.diluted_shares_schedule()
        assert all(v is None for v in schedule.values())


class TestStableShares:
    def test_no_ca_data_holds_constant(self):
        sr = build_share_rollforward(
            ticker="DBD", fact_table=_ft_with_shares(),
            fy_periods=_PERIODS, forecast_labels=_LABELS,
        )
        sched = sr.diluted_shares_schedule()
        vals = [v for v in sched.values() if v is not None]
        # All should equal base shares (no dilution)
        assert all(abs(v - vals[0]) < 0.001 for v in vals)

    def test_stable_method_label(self):
        sr = build_share_rollforward(
            ticker="DBD", fact_table=_ft_with_shares(),
            fy_periods=_PERIODS, forecast_labels=_LABELS,
        )
        assert all(row.method == "stable" for row in sr.forecast_rows)

    def test_stable_warns_about_no_ca(self):
        sr = build_share_rollforward(
            ticker="DBD", fact_table=_ft_with_shares(),
            fy_periods=_PERIODS, forecast_labels=_LABELS,
        )
        assert any("corporate action" in w.lower() for w in sr.warnings)


class TestCorporateActions:
    def test_issuance_increases_ending_shares(self):
        ca = [CorporateAction(forecast_label="2026F", issuance_mn=23.3)]
        sr = build_share_rollforward(
            ticker="DBD", fact_table=_ft_with_shares(94_450_000),
            fy_periods=_PERIODS, forecast_labels=_LABELS,
            corporate_actions=ca,
        )
        row = sr.forecast_rows[0]
        assert row.label == "2026F"
        expected_ending = 94.45 + 23.3
        assert abs(row.ending_shares_mn - expected_ending) < 0.01

    def test_buyback_reduces_ending_shares(self):
        ca = [CorporateAction(forecast_label="2026F", buyback_mn=5.0)]
        sr = build_share_rollforward(
            ticker="DBD", fact_table=_ft_with_shares(94_450_000),
            fy_periods=_PERIODS, forecast_labels=_LABELS,
            corporate_actions=ca,
        )
        row = sr.forecast_rows[0]
        assert abs(row.ending_shares_mn - (94.45 - 5.0)) < 0.01

    def test_diluted_includes_unvested_options(self):
        ca = [CorporateAction(forecast_label="2026F", issuance_mn=1.5, unvested_options_mn=0.5)]
        sr = build_share_rollforward(
            ticker="DBD", fact_table=_ft_with_shares(94_450_000),
            fy_periods=_PERIODS, forecast_labels=_LABELS,
            corporate_actions=ca,
        )
        row = sr.forecast_rows[0]
        # diluted = ending + unvested = (94.45 + 1.5) + 0.5 = 96.45
        assert abs(row.diluted_shares_mn - (94.45 + 1.5 + 0.5)) < 0.01

    def test_ca_carries_forward_to_next_year(self):
        """After an issuance in 2026F, 2027F begins with the post-issuance shares."""
        ca = [CorporateAction(forecast_label="2026F", issuance_mn=23.3)]
        sr = build_share_rollforward(
            ticker="DBD", fact_table=_ft_with_shares(94_450_000),
            fy_periods=_PERIODS, forecast_labels=["2026F", "2027F"],
            corporate_actions=ca,
        )
        row_2027 = sr.forecast_rows[1]
        assert abs(row_2027.beginning_shares_mn - (94.45 + 23.3)) < 0.01

    def test_formula_ending_shares_item32(self):
        """Item 32: Ending = Beginning + Issuance - Buyback."""
        ca = [
            CorporateAction(forecast_label="2026F", issuance_mn=10.0, buyback_mn=2.0),
            CorporateAction(forecast_label="2027F", issuance_mn=5.0),
        ]
        sr = build_share_rollforward(
            ticker="DBD", fact_table=_ft_with_shares(94_450_000),
            fy_periods=_PERIODS, forecast_labels=["2026F", "2027F"],
            corporate_actions=ca,
        )
        for row in sr.forecast_rows:
            if row.beginning_shares_mn is not None and row.ending_shares_mn is not None:
                expected = row.beginning_shares_mn + row.share_issuance_mn - row.share_buyback_mn
                assert abs(row.ending_shares_mn - expected) < 0.001


class TestDilutedSharesSchedule:
    def test_schedule_has_all_labels(self):
        sr = build_share_rollforward(
            ticker="DBD", fact_table=_ft_with_shares(),
            fy_periods=_PERIODS, forecast_labels=_LABELS,
        )
        sched = sr.diluted_shares_schedule()
        assert set(sched.keys()) == set(_LABELS)

    def test_to_dict_serializable(self):
        ca = [CorporateAction(forecast_label="2026F", issuance_mn=23.3, unvested_options_mn=1.5)]
        sr = build_share_rollforward(
            ticker="DBD", fact_table=_ft_with_shares(),
            fy_periods=_PERIODS, forecast_labels=_LABELS,
            corporate_actions=ca,
        )
        json.dumps(sr.to_dict())  # must not raise
