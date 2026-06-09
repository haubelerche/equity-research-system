"""Tests for BlendResult in blend.py (60% FCFF + 40% FCFE blend)."""
from __future__ import annotations

from backend.analytics.blend import blend_dcf, FCFF_WEIGHT, FCFE_WEIGHT


class TestBlendFormula:
    def test_official_blend_arithmetic(self):
        result = blend_dcf(
            ticker="DHG",
            price_fcff=60_000.0,
            price_fcfe=50_000.0,
            current_price_vnd=55_000.0,
        )
        expected = FCFF_WEIGHT * 60_000 + FCFE_WEIGHT * 50_000  # 36000 + 20000 = 56000
        assert result.target_price_dcf == expected

    def test_weights_are_60_40(self):
        assert FCFF_WEIGHT == 0.60
        assert FCFE_WEIGHT == 0.40

    def test_formula_string_in_to_dict(self):
        result = blend_dcf(ticker="DHG", price_fcff=60_000, price_fcfe=50_000)
        d = result.to_dict()
        assert "FCFF" in d["formula"]
        assert "FCFE" in d["formula"]
        assert "P/E" not in d["formula"]


class TestBlendDraftFlag:
    def test_normal_blend_is_not_draft_only(self):
        result = blend_dcf(
            ticker="DHG",
            price_fcff=60_000.0,
            price_fcfe=58_000.0,  # gap ~ 3.4% -- within 25%
            current_price_vnd=55_000.0,
        )
        assert result.is_draft_only is False

    def test_gap_above_threshold_sets_draft_only(self):
        result = blend_dcf(
            ticker="DHG",
            price_fcff=90_000.0,
            price_fcfe=50_000.0,  # gap = 80% -- above 25%
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
            price_fcfe=50_000.0,  # gap ~ 25.2%
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
        assert result.target_price_dcf == 70_000.0  # 100% FCFF fallback

    def test_partial_price_fcff_none_sets_draft_only(self):
        result = blend_dcf(
            ticker="DHG",
            price_fcff=None,
            price_fcfe=60_000.0,
            current_price_vnd=55_000.0,
        )
        assert result.is_draft_only is True
        assert result.target_price_dcf == 60_000.0  # 100% FCFE fallback

    def test_both_none_gives_no_target(self):
        result = blend_dcf(
            ticker="DHG",
            price_fcff=None,
            price_fcfe=None,
            current_price_vnd=55_000.0,
        )
        assert result.target_price_dcf is None

    def test_to_dict_includes_is_draft_only(self):
        result = blend_dcf(
            ticker="DHG",
            price_fcff=90_000.0,
            price_fcfe=50_000.0,
            current_price_vnd=55_000.0,
        )
        d = result.to_dict()
        assert "is_draft_only" in d
        assert d["is_draft_only"] is True

    def test_to_dict_has_fcfe_not_pe(self):
        result = blend_dcf(
            ticker="DHG",
            price_fcff=60_000.0,
            price_fcfe=58_000.0,
            current_price_vnd=55_000.0,
        )
        d = result.to_dict()
        assert "price_fcfe_vnd" in d
        assert "price_pe_forward_vnd" not in d
        assert d["fcfe_weight"] == 0.40


class TestBlendUpside:
    def test_upside_calculation(self):
        result = blend_dcf(
            ticker="DHG",
            price_fcff=60_000.0,
            price_fcfe=50_000.0,
            current_price_vnd=50_000.0,
        )
        # target = 0.6*60000 + 0.4*50000 = 56000
        # upside = (56000 - 50000) / 50000 = 0.12
        assert result.upside_pct is not None
        assert abs(result.upside_pct - 0.12) < 1e-6

    def test_margin_of_safety(self):
        result = blend_dcf(
            ticker="DHG",
            price_fcff=60_000.0,
            price_fcfe=50_000.0,
            current_price_vnd=50_000.0,
        )
        # mos = (56000 - 50000) / 56000
        expected_mos = 6000 / 56000
        assert result.margin_of_safety is not None
        assert abs(result.margin_of_safety - expected_mos) < 1e-6


class TestBlendTVWeight:
    def test_tv_weight_warning_above_70pct(self):
        result = blend_dcf(
            ticker="DHG",
            price_fcff=60_000.0,
            price_fcfe=58_000.0,
            pv_terminal_value_fcff=800.0,
            enterprise_value_fcff=1000.0,  # TV weight = 80%
        )
        assert result.tv_weight_fcff is not None
        assert result.tv_weight_fcff == 0.8
        assert any("Terminal value" in w for w in result.warnings)

    def test_tv_weight_no_warning_below_70pct(self):
        result = blend_dcf(
            ticker="DHG",
            price_fcff=60_000.0,
            price_fcfe=58_000.0,
            pv_terminal_value_fcff=600.0,
            enterprise_value_fcff=1000.0,  # TV weight = 60%
        )
        assert not any("Terminal value" in w for w in result.warnings)
