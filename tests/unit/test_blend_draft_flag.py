"""Tests for BlendResult.is_draft_only flag in blend.py (FCFF + P/E Forward blend)."""
from __future__ import annotations

from backend.analytics.blend import blend_dcf


class TestBlendDraftFlag:
    def test_normal_blend_is_not_draft_only(self):
        result = blend_dcf(
            ticker="DHG",
            price_fcff=60_000.0,
            price_pe_forward=58_000.0,  # gap ≈ 3.4% — within 40%
            current_price_vnd=55_000.0,
        )
        assert result.is_draft_only is False

    def test_gap_above_threshold_sets_draft_only(self):
        result = blend_dcf(
            ticker="DHG",
            price_fcff=90_000.0,
            price_pe_forward=50_000.0,  # gap = 80% — above 40%
            current_price_vnd=55_000.0,
        )
        assert result.is_draft_only is True

    def test_gap_exactly_at_threshold_not_draft_only(self):
        # exactly 40% should NOT set draft_only (threshold is strictly >)
        result = blend_dcf(
            ticker="DHG",
            price_fcff=70_000.0,
            price_pe_forward=50_000.0,  # gap = 40.0% exactly
            current_price_vnd=55_000.0,
        )
        assert result.is_draft_only is False

    def test_gap_just_above_threshold_is_draft_only(self):
        result = blend_dcf(
            ticker="DHG",
            price_fcff=70_100.0,
            price_pe_forward=50_000.0,  # gap ≈ 40.2%
            current_price_vnd=55_000.0,
        )
        assert result.is_draft_only is True

    def test_partial_price_pe_forward_none_sets_draft_only(self):
        result = blend_dcf(
            ticker="DHG",
            price_fcff=70_000.0,
            price_pe_forward=None,
            current_price_vnd=55_000.0,
        )
        assert result.is_draft_only is True

    def test_partial_price_fcff_none_sets_draft_only(self):
        result = blend_dcf(
            ticker="DHG",
            price_fcff=None,
            price_pe_forward=60_000.0,
            current_price_vnd=55_000.0,
        )
        assert result.is_draft_only is True

    def test_to_dict_includes_is_draft_only(self):
        result = blend_dcf(
            ticker="DHG",
            price_fcff=90_000.0,
            price_pe_forward=50_000.0,
            current_price_vnd=55_000.0,
        )
        d = result.to_dict()
        assert "is_draft_only" in d
        assert d["is_draft_only"] is True

    def test_to_dict_false_when_normal(self):
        result = blend_dcf(
            ticker="DHG",
            price_fcff=60_000.0,
            price_pe_forward=58_000.0,
            current_price_vnd=55_000.0,
        )
        d = result.to_dict()
        assert d["is_draft_only"] is False
