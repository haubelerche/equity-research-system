"""Spec B: BALANCE_SHEET_IDENTITY_GATE — forecast must satisfy Assets = Liabilities + Equity."""
from __future__ import annotations

from backend.harness.gates import balance_sheet_identity_gate


def _fy(label, assets, equity, debt, other):
    return {"label": label, "total_assets": assets, "equity": equity,
            "total_debt": debt, "other_liabilities": other}


def test_passes_when_balanced():
    model = {"forecast_years": [
        _fy("2026F", 5896.3, 4859.7, 0.0, 1036.6),
        _fy("2027F", 6648.0, 5611.4, 0.0, 1036.6),
    ]}
    g = balance_sheet_identity_gate(model)
    assert g["passed"] is True


def test_fails_when_imbalanced_beyond_half_percent():
    # assets 5896.3 vs L+E 5000 → imbalance ~896 >> 0.5% (29.5)
    model = {"forecast_years": [_fy("2026F", 5896.3, 4000.0, 0.0, 1000.0)]}
    g = balance_sheet_identity_gate(model)
    assert g["passed"] is False
    assert "2026F" in g["blocking_reasons"][0]


def test_passes_at_tolerance_boundary():
    # imbalance exactly 0.5% of assets should pass; just over should fail.
    assets = 1000.0
    just_in = _fy("2026F", assets, 900.0, 0.0, 100.0 - 5.0 + 0.001)  # imbalance ~4.999 < 5.0
    just_out = _fy("2027F", assets, 900.0, 0.0, 100.0 - 6.0)          # imbalance 6.0 > 5.0
    assert balance_sheet_identity_gate({"forecast_years": [just_in]})["passed"] is True
    assert balance_sheet_identity_gate({"forecast_years": [just_out]})["passed"] is False


def test_no_balance_sheet_years_does_not_hard_block():
    g = balance_sheet_identity_gate({"forecast_years": [{"label": "2026F"}]})
    # Cannot verify → not a hard critical failure (no silent pass either).
    assert g["passed"] is False
    assert g.get("severity") != "critical"
