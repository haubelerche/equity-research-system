"""AGM drivers → ForecastAssumptions mapping.

build_agm_assumptions turns the shareholder-approved 2026 plan into priority forecast
drivers WITH source/page provenance — and crucially does NOT launder them into a fake
analyst-approved flag (the debt-schedule auto-approve bug lesson).
"""
from __future__ import annotations

from backend.analytics.agm_drivers import build_agm_assumptions
from backend.analytics.forecasting import ForecastAssumptions


def test_revenue_growth_pct_becomes_fraction_override_with_provenance():
    pack = {"targets_2026": {"revenue": 5500.0, "revenue_growth_pct": 10.0, "page": 3}}
    out = build_agm_assumptions(pack)
    assert out["revenue_growth_override"] == 0.10
    src = out["driver_sources"]["revenue_growth_override"]
    assert src["source"] == "agm_2026" and src["page"] == 3 and src["value"] == 0.10


def test_borrowing_plan_becomes_pdf_debt_plan():
    pack = {"borrowing_plan": [
        {"year": 2026, "amount": 300.0, "description": "Vay nhà máy", "page": 8},
        {"year": None, "amount": 50.0, "page": 9},  # no year → dropped
    ]}
    out = build_agm_assumptions(pack)
    assert out["pdf_debt_plan"] == [
        {"year": 2026, "amount": 300.0, "description": "Vay nhà máy", "page": 8},
    ]
    assert out["driver_sources"]["pdf_debt_plan"]["source"] == "agm_2026"


def test_absolute_revenue_target_becomes_growth_when_no_pct():
    pack = {"targets_2026": {"revenue": 2090.0, "page": 2}}
    out = build_agm_assumptions(pack, latest_revenue=1900.0)
    assert out["revenue_growth_override"] == 0.1
    assert out["driver_sources"]["revenue_growth_override"]["source"] == "agm_2026"


def test_explicit_growth_pct_wins_over_absolute_target():
    pack = {"targets_2026": {"revenue": 2090.0, "revenue_growth_pct": 8.0, "page": 2}}
    out = build_agm_assumptions(pack, latest_revenue=1900.0)
    assert out["revenue_growth_override"] == 0.08


def test_absolute_target_ignored_without_latest_revenue():
    pack = {"targets_2026": {"revenue": 2090.0, "page": 2}}
    out = build_agm_assumptions(pack)
    assert "revenue_growth_override" not in out


def test_does_not_set_analyst_approved_status():
    pack = {"targets_2026": {"revenue_growth_pct": 10.0, "page": 3}}
    out = build_agm_assumptions(pack)
    assert "assumption_status" not in out
    assert out.get("debt_schedule_approved") is not True


def test_empty_pack_yields_no_overrides():
    out = build_agm_assumptions({})
    assert out["driver_sources"] == {}
    assert "revenue_growth_override" not in out
    assert "pdf_debt_plan" not in out


def test_output_is_valid_forecast_assumptions_kwargs():
    pack = {"targets_2026": {"revenue_growth_pct": 12.0, "page": 3},
            "borrowing_plan": [{"year": 2026, "amount": 0.0, "page": 8}]}
    out = build_agm_assumptions(pack)
    # driver_sources is carried on ForecastAssumptions for provenance display.
    fa = ForecastAssumptions(**out)
    assert fa.revenue_growth_override == 0.12
    assert fa.driver_sources["revenue_growth_override"]["source"] == "agm_2026"
