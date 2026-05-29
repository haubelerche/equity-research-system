"""Tests for BlendResult.is_draft_only flag in blend.py."""
from __future__ import annotations

import pytest

from backend.analytics.blend import blend_dcf


class TestBlendDraftFlag:
    def test_normal_blend_is_not_draft_only(self):
        result = blend_dcf(
            ticker="DHG",
            price_fcff=60_000.0,
            price_fcfe=58_000.0,  # gap ≈ 3.4% — within 25%
            current_price_vnd=55_000.0,
        )
        assert result.is_draft_only is False

    def test_gap_above_threshold_sets_draft_only(self):
        result = blend_dcf(
            ticker="DHG",
            price_fcff=80_000.0,
            price_fcfe=50_000.0,  # gap = 60% — above 25%
            current_price_vnd=55_000.0,
        )
        assert result.is_draft_only is True

    def test_gap_exactly_at_threshold_not_draft_only(self):
        # exactly 25% should NOT set draft_only (threshold is strictly >)
        result = blend_dcf(
            ticker="DHG",
            price_fcff=62_500.0,
            price_fcfe=50_000.0,  # gap = 25.0% exactly
            current_price_vnd=55_000.0,
        )
        assert result.is_draft_only is False

    def test_gap_just_above_threshold_is_draft_only(self):
        result = blend_dcf(
            ticker="DHG",
            price_fcff=62_600.0,
            price_fcfe=50_000.0,  # gap ≈ 25.2%
            current_price_vnd=55_000.0,
        )
        assert result.is_draft_only is True

    def test_partial_price_fcfe_none_sets_draft_only(self):
        result = blend_dcf(
            ticker="DHG",
            price_fcff=70_000.0,
            price_fcfe=None,
            current_price_vnd=55_000.0,
        )
        assert result.is_draft_only is True

    def test_partial_price_fcff_none_sets_draft_only(self):
        result = blend_dcf(
            ticker="DHG",
            price_fcff=None,
            price_fcfe=60_000.0,
            current_price_vnd=55_000.0,
        )
        assert result.is_draft_only is True

    def test_to_dict_includes_is_draft_only(self):
        result = blend_dcf(
            ticker="DHG",
            price_fcff=80_000.0,
            price_fcfe=50_000.0,
            current_price_vnd=55_000.0,
        )
        d = result.to_dict()
        assert "is_draft_only" in d
        assert d["is_draft_only"] is True

    def test_to_dict_false_when_normal(self):
        result = blend_dcf(
            ticker="DHG",
            price_fcff=60_000.0,
            price_fcfe=58_000.0,
            current_price_vnd=55_000.0,
        )
        d = result.to_dict()
        assert d["is_draft_only"] is False
