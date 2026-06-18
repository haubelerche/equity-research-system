"""Regression: client report view model resolves against the harness manifest.

The six-agent harness manifest registers a single ``valuation`` artifact
(valuation.json) plus ``facts``, but no separate ``valuation_result``/``fcff``/
``blend``/``forecast`` keys. The view-model resolvers must tolerate those missing
keys and fall back to the valuation.json sub-sections instead of raising.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.reporting import client_report_view_model as vm


class _StubManifest:
    def __init__(self, artifacts: dict[str, dict]) -> None:
        self._artifacts = artifacts

    def resolve(self, key: str):
        return key if key in self._artifacts else None

    def load_json(self, key: str) -> dict:
        return self._artifacts.get(key, {})


def test_resolve_json_returns_empty_for_missing_key():
    manifest = _StubManifest({"valuation": {"x": 1}})
    assert vm._resolve_json("valuation.json", manifest, "valuation_result", False) == {}


def test_resolve_json_raises_without_manifest():
    with pytest.raises(ValueError):
        vm._resolve_json("valuation.json", None, "valuation", False)


def test_valuation_result_falls_back_to_full_valuation_artifact():
    val = {"is_publishable": "true", "blend_dcf": {"target_price_dcf_vnd": 100000}}
    manifest = _StubManifest({"valuation": val})  # no valuation_result key
    assert vm._valuation_result("DHG", manifest, False) == val


def test_fcff_blend_forecast_fall_back_to_valuation_subsections():
    val = {
        "fcff": {"fcff_table": [{"year": "2026F"}], "wacc": 0.12},
        "blend_dcf": {"target_price_dcf_vnd": 100000},
        "forecast": {"forecast_years": [{"label": "2026F"}]},
    }
    manifest = _StubManifest({"valuation": val})
    assert vm._fcff("DHG", manifest, False) == val["fcff"]
    assert vm._blend("DHG", manifest, False) == val["blend_dcf"]
    assert vm._forecast("DHG", manifest, False) == val["forecast"]


def test_display_governance_shows_target_even_when_no_method_eligible():
    # Option B: the gate never blanks the client-facing target. "no eligible
    # method" is surfaced as internal metadata only; the computed value still shows.
    valuation = {
        "valuation_method_policy": {
            "selected_methods": [],
            "status": "draft_only",
        }
    }
    blend = {
        "current_price_vnd": 50_200,
        "target_price_dcf_vnd": 27_207,
        "upside_pct": -0.458,
        "is_draft_only": True,
    }

    display = vm._report_display_governance("standard", valuation, blend)

    assert display["current_price"] == 50_200
    assert display["target_price"] == 27_207
    assert display["upside"] is not None
    assert display["blend_target_price"] == 27_207
    assert display["recommendation"] == "Đang rà soát"
    # The readiness signal is still available to the export workflow as metadata.
    assert "no_eligible_valuation_method" in display["blocking_reasons"]


def test_display_governance_shows_low_confidence_target():
    valuation = {
        "valuation_method_policy": {"selected_methods": ["FCFF"], "status": "draft_only"},
        "valuation_confidence": {"fcff_dcf": "low"},
    }
    blend = {
        "current_price_vnd": 50_200,
        "target_price_dcf_vnd": 27_207,
        "upside_pct": -0.458,
        "is_draft_only": True,
    }

    display = vm._report_display_governance("standard", valuation, blend)

    assert display["target_price"] == 27_207
    assert display["recommendation"] == "Đang rà soát"


def test_market_price_as_of_prefers_run_market_data_date():
    market_data = SimpleNamespace(
        as_of_date="2026-06-16",
        trading_statistics=SimpleNamespace(last_close=102.0),
    )

    assert vm._market_price_as_of(
        102_000.0,
        valuation={"snapshot_as_of": "2026-06-15"},
        market_data=market_data,
    ) == "2026-06-16"


def test_market_price_as_of_falls_back_to_valuation_snapshot_date():
    assert vm._market_price_as_of(
        50_200.0,
        valuation={"snapshot_as_of": "2026-06-16T04:00:00+00:00"},
    ) == "2026-06-16"


def test_valuation_summary_shows_low_confidence_methods():
    # Option B: the valuation results table shows computed method values even at
    # low confidence — caveats live in the disclosures, not in a hidden table.
    valuation = {
        "selected_methods": ["FCFF"],
        "method_weights": {"FCFF": 100.0},
        "valuation_confidence": {"fcff_dcf": "low"},
        "fcff": {"target_price_vnd": 27_207},
        "blend_dcf": {"target_price_dcf_vnd": 27_207},
    }

    table = vm._table_valuation_summary(valuation)
    assert table is not None
    assert "FCFF" in [row[0] for row in table.rows]


def test_recommendation_has_three_issued_states_plus_unrated_state():
    labels = {
        vm._recommendation(0.25, "analyst_draft", approved_for_display=True),
        vm._recommendation(0.00, "analyst_draft", approved_for_display=True),
        vm._recommendation(-0.15, "analyst_draft", approved_for_display=True),
        vm._recommendation(None, "analyst_draft", approved_for_display=False),
    }

    assert labels == {"Mua", "Giữ", "Bán", "Không xếp hạng"}


def test_forecast_rows_are_enriched_from_debt_dividend_and_cash_schedules():
    forecast = {
        "forecast_years": [{"label": "2026F", "revenue": 1000.0}],
        "cash_sweep_artifact": {
            "year_results": [{"year_label": "2026F", "computed_ending_cash": 120.0}]
        },
        "debt_schedule": {
            "is_fcfe_publishable": True,
            "forecast_rows": [{
                "label": "2026F",
                "beginning_interest_bearing_debt": 180.0,
                "ending_interest_bearing_debt": 200.0,
                "net_borrowing": 20.0,
            }]
        },
        "dividend_schedule": {
            "forecast_rows": [{
                "label": "2026F",
                "cash_dividend": 50.0,
                "payout_ratio": 0.5,
                "retained_earnings_addition": 50.0,
            }]
        },
    }

    rows = vm._forecast_by_label(forecast)

    assert rows["2026F"]["cash"] == pytest.approx(120.0)
    assert rows["2026F"]["total_debt"] == pytest.approx(200.0)
    assert rows["2026F"]["net_borrowing"] == pytest.approx(20.0)
    assert rows["2026F"]["cash_dividend"] == pytest.approx(50.0)


def test_forecast_cash_is_not_enriched_when_dividend_policy_is_missing():
    forecast = {
        "forecast_years": [{"label": "2026F", "revenue": 1000.0, "cash": 999.0}],
        "cash_sweep_artifact": {
            "year_results": [{"year_label": "2026F", "computed_ending_cash": 1200.0}]
        },
        "dividend_schedule": {"method": "missing", "forecast_rows": []},
    }

    rows = vm._forecast_by_label(forecast)

    assert rows["2026F"]["cash"] is None


def test_forecast_debt_level_shown_but_flow_gated_for_stable_debt():
    """A debt-bearing company forecast as held-flat (stable_debt, FCFE-blocked) MUST
    still show its debt LEVEL — hiding it makes a leveraged issuer look debt-free.
    Only the net_borrowing FLOW (which feeds FCFE) stays suppressed."""
    forecast = {
        "forecast_years": [{
            "label": "2026F",
            "revenue": 1000.0,
            "total_debt": 4409.0,
            "beginning_debt": 4409.0,
            "ending_debt": 4409.0,
            "net_borrowing": 0.0,
        }],
        "debt_schedule": {
            "is_fcfe_publishable": False,
            "forecast_method": "stable_debt",
            "status": "low",
            "forecast_rows": [{
                "label": "2026F",
                "beginning_interest_bearing_debt": 4409.0,
                "ending_interest_bearing_debt": 4409.0,
                "net_borrowing": 0.0,
            }],
        },
    }

    rows = vm._forecast_by_label(forecast)

    # Debt level is a balance-sheet position → shown.
    assert rows["2026F"]["total_debt"] == pytest.approx(4409.0)
    assert rows["2026F"]["ending_debt"] == pytest.approx(4409.0)
    # net_borrowing flow feeds FCFE → gated when not FCFE-publishable.
    assert rows["2026F"]["net_borrowing"] is None


def test_forecast_debt_level_enriched_from_schedule_when_year_row_missing_it():
    """When forecast_years lacks total_debt (e.g. older artifact) but the debt
    schedule carries an anchored ending balance, the level is backfilled so the
    report shows debt rather than a dash."""
    forecast = {
        "forecast_years": [{"label": "2026F", "revenue": 1000.0}],
        "debt_schedule": {
            "is_fcfe_publishable": False,
            "forecast_method": "stable_debt",
            "status": "low",
            "forecast_rows": [{
                "label": "2026F",
                "beginning_interest_bearing_debt": 4409.0,
                "ending_interest_bearing_debt": 4409.0,
                "net_borrowing": 0.0,
            }],
        },
    }

    rows = vm._forecast_by_label(forecast)

    assert rows["2026F"]["total_debt"] == pytest.approx(4409.0)
    assert rows["2026F"]["net_borrowing"] is None


def test_forecast_debt_is_hidden_when_publishability_flag_is_missing():
    forecast = {
        "forecast_years": [{
            "label": "2026F",
            "revenue": 1000.0,
            "total_debt": 343.0,
            "net_borrowing": 343.0,
        }],
        "debt_schedule": {
            "forecast_rows": [{
                "label": "2026F",
                "ending_interest_bearing_debt": 343.0,
                "net_borrowing": 343.0,
            }],
        },
    }

    rows = vm._forecast_by_label(forecast)

    assert rows["2026F"]["total_debt"] is None
    assert rows["2026F"]["net_borrowing"] is None


def test_forecast_debt_is_hidden_when_method_contradicts_publishability_flag():
    forecast = {
        "forecast_years": [{
            "label": "2026F",
            "revenue": 1000.0,
            "total_debt": 343.0,
            "net_borrowing": 343.0,
        }],
        "debt_schedule": {
            "is_fcfe_publishable": True,
            "forecast_method": "target_debt_ratio",
            "status": "low",
            "forecast_rows": [{
                "label": "2026F",
                "ending_interest_bearing_debt": 343.0,
                "net_borrowing": 343.0,
            }],
        },
    }

    rows = vm._forecast_by_label(forecast)

    assert rows["2026F"]["total_debt"] is None
    assert rows["2026F"]["net_borrowing"] is None


def test_financial_summary_omits_dividend_rows():
    forecast_rows = {
        "2026F": {
            "revenue": 1000.0,
            "net_income": 100.0,
            "eps": 1000.0,
            "equity": 500.0,
            "total_debt": 300.0,
            "cash": 100.0,
            "ebitda": 200.0,
            "cash_dividend": 50.0,
            "diluted_shares": 100.0,
            "total_assets": 900.0,
        }
    }

    table = vm._table_financial_summary(
        facts={},
        forecast_rows=forecast_rows,
        current_price=10_000.0,
        periods=["2026F"],
        dividend_per_share=None,
        shares_mn=100.0,
    )
    rows = {label: values for label, values in table.rows}

    assert rows["Nợ ròng / EBITDA"][0] == pytest.approx(1.0)
    assert rows["P/B"][0] == pytest.approx(2.0)
    assert "Cổ tức/cp" not in rows
    assert "Suất sinh lợi cổ tức" not in rows


def test_profitability_table_ev_ebitda_includes_net_debt_and_dividend_yield():
    forecast_rows = {
        "2026F": {
            "revenue": 1000.0,
            "net_income": 100.0,
            "eps": 1000.0,
            "equity": 500.0,
            "total_debt": 300.0,
            "cash": 100.0,
            "ebit": 160.0,
            "ebitda": 200.0,
            "cash_dividend": 50.0,
            "diluted_shares": 100.0,
            "total_assets": 900.0,
        }
    }

    table = vm._table_profitability_valuation(
        facts={},
        forecast_rows=forecast_rows,
        current_price=10_000.0,
        fcff={"wacc": 0.12, "wacc_breakdown": {"tax_rate": 0.2}},
        periods=["2026F"],
        shares_mn=100.0,
        dividend_per_share=None,
    )
    rows = {label: values for label, values in table.rows}

    assert rows["EV/EBITDA"][0] == pytest.approx(6.0)
    assert rows["P/B"][0] == pytest.approx(2.0)
    assert rows["Suất sinh lợi cổ tức"][0] == pytest.approx(0.05)
