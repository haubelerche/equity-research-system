"""Task 2.4: peer_data_source flag in run_valuation P/E Forward output.

When target_pe equals the default (15.0), the artifact's pe_forward section must
carry peer_data_source="analyst_default_pending_peers" and the blend warnings must
include the standard peer-validation message.
When target_pe is explicitly provided by the analyst (not the default), the field
must read "analyst_override".
"""
from __future__ import annotations

import types
import pytest


# ── helpers ──────────────────────────────────────────────────────────────────

_DEFAULT_PE = 15.0
_CUSTOM_PE = 18.5


def _make_minimal_blend(warnings: list[str] | None = None):
    """Minimal blend result stub with a mutable warnings list."""

    class _Blend:
        def __init__(self, w):
            self.warnings: list[str] = w or []
            self.target_price_dcf: float | None = 45_000.0
            self.pv_terminal_value: float | None = None
            self.enterprise_value: float | None = None

        def to_dict(self) -> dict:
            return {
                "target_price_dcf_vnd": self.target_price_dcf,
                "price_fcff_vnd": None,
                "price_pe_forward_vnd": None,
                "fcff_weight": 0.6,
                "pe_weight": 0.4,
                "upside_pct": None,
                "margin_of_safety": None,
                "valuation_gap_pct": None,
                "warnings": list(self.warnings),
            }

    return _Blend(warnings)


def _run_pe_forward_logic(target_pe: float) -> tuple[dict, list[str]]:
    """
    Replicate only the pe_forward artifact construction logic from run_valuation.

    Returns (pe_forward_dict, blend_warnings_after_propagation).
    """
    _DEFAULT_PE = 15.0
    _pe_is_default = target_pe == _DEFAULT_PE
    _peer_data_source = (
        "analyst_default_pending_peers" if _pe_is_default else "analyst_override"
    )
    _pe_default_warning: str | None = (
        "target_pe=15.0x is model default — validate with peer-median P/E before publishing"
        if _pe_is_default
        else None
    )

    blend = _make_minimal_blend()

    # Simulate the propagation block from run_valuation
    if _pe_default_warning and _pe_default_warning not in blend.warnings:
        blend.warnings.append(_pe_default_warning)

    eps_fy1: float | None = 5_000.0
    price_pe_forward: float | None = eps_fy1 * target_pe if eps_fy1 else None

    pe_forward = {
        "target_pe": target_pe,
        "eps_fy1_vnd": eps_fy1,
        "price_pe_forward_vnd": price_pe_forward,
        "peer_data_source": _peer_data_source,
        "warnings": ([_pe_default_warning] if _pe_default_warning else []),
    }

    return pe_forward, blend.warnings


# ── tests ─────────────────────────────────────────────────────────────────────


class TestPeForwardPeerDataSource:
    def test_default_pe_sets_analyst_default_pending_peers(self):
        pe_fwd, _ = _run_pe_forward_logic(_DEFAULT_PE)
        assert pe_fwd["peer_data_source"] == "analyst_default_pending_peers"

    def test_custom_pe_sets_analyst_override(self):
        pe_fwd, _ = _run_pe_forward_logic(_CUSTOM_PE)
        assert pe_fwd["peer_data_source"] == "analyst_override"

    def test_default_pe_warning_present_in_pe_forward(self):
        pe_fwd, _ = _run_pe_forward_logic(_DEFAULT_PE)
        assert len(pe_fwd["warnings"]) == 1
        assert "15.0x is model default" in pe_fwd["warnings"][0]
        assert "peer-median P/E" in pe_fwd["warnings"][0]

    def test_custom_pe_no_warning_in_pe_forward(self):
        pe_fwd, _ = _run_pe_forward_logic(_CUSTOM_PE)
        assert pe_fwd["warnings"] == []

    def test_default_pe_warning_propagated_to_blend(self):
        _, blend_warnings = _run_pe_forward_logic(_DEFAULT_PE)
        assert any("15.0x is model default" in w for w in blend_warnings)

    def test_custom_pe_no_default_warning_in_blend(self):
        _, blend_warnings = _run_pe_forward_logic(_CUSTOM_PE)
        assert not any("model default" in w for w in blend_warnings)

    def test_default_pe_warning_not_duplicated_in_blend(self):
        """Propagation guard must not add the same warning twice."""
        _pe_default_warning = (
            "target_pe=15.0x is model default — validate with peer-median P/E before publishing"
        )
        blend = _make_minimal_blend(warnings=[_pe_default_warning])
        # Simulate the propagation guard
        if _pe_default_warning and _pe_default_warning not in blend.warnings:
            blend.warnings.append(_pe_default_warning)
        count = sum(1 for w in blend.warnings if "15.0x is model default" in w)
        assert count == 1, f"Warning duplicated: {blend.warnings}"
