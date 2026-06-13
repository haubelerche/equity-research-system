from __future__ import annotations

from types import SimpleNamespace


def test_fcff_sensitivity_default_range_centers_on_base_wacc(monkeypatch):
    from backend.analytics.fcff import WACCAssumptions
    from backend.analytics.sensitivity import build_fcff_sensitivity_table

    def fake_compute_fcff(**kwargs):
        return SimpleNamespace(target_price_vnd=10000.0, warnings=[])

    monkeypatch.setattr("backend.analytics.fcff.compute_fcff", fake_compute_fcff)

    table = build_fcff_sensitivity_table(
        ticker="DBD",
        forecast=object(),
        fact_table={},
        base_wacc_assumptions=WACCAssumptions(wacc_override=0.138),
        g_range=[0.03],
        shares_mn=100.0,
    )

    assert table["wacc_range"] == [0.118, 0.128, 0.138, 0.148, 0.158]
    assert table["base_wacc"] == 0.138


def test_fcfe_sensitivity_default_range_centers_on_base_re(monkeypatch):
    from backend.analytics.fcfe import CostOfEquityAssumptions
    from backend.analytics.sensitivity import build_fcfe_sensitivity_table

    def fake_compute_fcfe(**kwargs):
        return SimpleNamespace(target_price_vnd=9000.0, warnings=[])

    monkeypatch.setattr("backend.analytics.fcfe.compute_fcfe", fake_compute_fcfe)

    table = build_fcfe_sensitivity_table(
        ticker="DBD",
        forecast=object(),
        fact_table={},
        base_coe_assumptions=CostOfEquityAssumptions(re_override=0.138),
        g_range=[0.03],
        shares_mn=100.0,
    )

    assert table["re_range"] == [0.118, 0.128, 0.138, 0.148, 0.158]
