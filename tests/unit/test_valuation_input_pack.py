from __future__ import annotations

from datetime import date

from backend.analytics.forecasting import ForecastAssumptions, run_forecast
from backend.analytics.share_rollforward import build_share_rollforward
from backend.facts.normalizer import FactEntry
from backend.valuation.input_pack_builder import build_valuation_input_pack
from backend.valuation.manual_packs import load_manual_packs


def _entry(value: float) -> FactEntry:
    return FactEntry(value=value, source_id="test", source_uri="test://fact", confidence=0.95)


def _fact_table() -> dict[str, dict[str, FactEntry]]:
    return {
        "revenue.net": {"2024FY": _entry(5_000.0), "2025FY": _entry(5_500.0)},
        "gross_profit.total": {"2024FY": _entry(2_000.0), "2025FY": _entry(2_250.0)},
        "cogs.total": {"2024FY": _entry(-3_000.0), "2025FY": _entry(-3_250.0)},
        "sga.total": {"2024FY": _entry(-1_000.0), "2025FY": _entry(-1_100.0)},
        "profit_before_tax.total": {"2024FY": _entry(900.0), "2025FY": _entry(1_000.0)},
        "tax_expense.total": {"2024FY": _entry(-180.0), "2025FY": _entry(-200.0)},
        "net_income.parent": {"2024FY": _entry(720.0), "2025FY": _entry(800.0)},
        "eps.basic": {"2024FY": _entry(5_500.0), "2025FY": _entry(6_100.0)},
        "total_assets.ending": {"2024FY": _entry(7_000.0), "2025FY": _entry(7_500.0)},
        "equity.parent": {"2024FY": _entry(4_500.0), "2025FY": _entry(5_000.0)},
        "cash_and_equivalents.ending": {"2024FY": _entry(1_000.0), "2025FY": _entry(1_100.0)},
        "short_term_investments.ending": {"2024FY": _entry(200.0), "2025FY": _entry(250.0)},
        "short_term_debt.ending": {"2024FY": _entry(100.0), "2025FY": _entry(120.0)},
        "long_term_debt.ending": {"2024FY": _entry(300.0), "2025FY": _entry(280.0)},
        "total_debt.ending": {"2024FY": _entry(400.0), "2025FY": _entry(400.0)},
        "interest_expense.total": {"2024FY": _entry(-30.0), "2025FY": _entry(-32.0)},
        "operating_cash_flow.total": {"2024FY": _entry(850.0), "2025FY": _entry(920.0)},
        "capex.total": {"2024FY": _entry(-120.0), "2025FY": _entry(-150.0)},
        "depreciation.total": {"2024FY": _entry(100.0), "2025FY": _entry(110.0)},
        "proceeds_from_borrowings.total": {"2024FY": _entry(50.0), "2025FY": _entry(60.0)},
        "repayment_of_borrowings.total": {"2024FY": _entry(-40.0), "2025FY": _entry(-60.0)},
        "shares_outstanding.ending": {"2025FY": _entry(130.0)},
    }


def test_manual_pack_loaders_accept_only_accepted_records(tmp_path):
    (tmp_path / "market_prices.csv").write_text(
        "as_of_date,ticker,price,status,source\n"
        "2026-01-01,DHG,90000,,manual\n"
        "2026-01-02,DHG,91000,draft,manual\n"
        "2026-01-03,DHG,92000,accepted,manual\n",
        encoding="utf-8",
    )
    (tmp_path / "shares_outstanding.csv").write_text(
        "as_of_date,ticker,shares_outstanding,status,source\n"
        "2026-01-03,DHG,130746071,accepted,manual\n",
        encoding="utf-8",
    )
    (tmp_path / "peer_multiples.csv").write_text(
        "as_of_date,ticker,peer_group,pe_ttm,ev_ebitda_ttm,status,source\n"
        "2026-01-03,DHG,pharma_vn,15,10,accepted,manual\n"
        "2026-01-03,IMP,pharma_vn,17,12,accepted,manual\n",
        encoding="utf-8",
    )
    (tmp_path / "corporate_actions.csv").write_text(
        "ticker,event_date,event_type,shares_before,shares_after,ratio,cash_amount_vnd,source,status\n",
        encoding="utf-8",
    )
    for name in ["debt_policy", "wacc_assumptions", "tax_policy", "working_capital_policy"]:
        (tmp_path / f"{name}.yaml").write_text(
            "defaults:\n  status: accepted\n  source: manual\n",
            encoding="utf-8",
        )

    bundle = load_manual_packs("DHG", date(2026, 1, 4), manual_dir=tmp_path)

    assert bundle.market["price"] == 92000
    assert bundle.shares["shares_outstanding"] == 130746071
    assert bundle.peers["peer_pe_median"] == 16
    assert any("missing status/source" in warning for warning in bundle.warnings)


def test_input_pack_builder_combines_facts_market_peers_and_policies(tmp_path):
    (tmp_path / "market_prices.csv").write_text("as_of_date,ticker,price,status,source\n", encoding="utf-8")
    (tmp_path / "shares_outstanding.csv").write_text(
        "as_of_date,ticker,shares_outstanding,status,source\n2026-01-03,DHG,130746071,accepted,manual\n",
        encoding="utf-8",
    )
    (tmp_path / "peer_multiples.csv").write_text(
        "as_of_date,ticker,peer_group,pe_ttm,ev_ebitda_ttm,status,source\n"
        "2026-01-03,DHG,pharma_vn,15,10,accepted,manual\n"
        "2026-01-03,IMP,pharma_vn,17,12,accepted,manual\n",
        encoding="utf-8",
    )
    (tmp_path / "corporate_actions.csv").write_text(
        "ticker,event_date,event_type,shares_before,shares_after,ratio,cash_amount_vnd,source,status\n"
        "DHG,2026-01-03,no_action,,,,,manual,accepted\n",
        encoding="utf-8",
    )
    (tmp_path / "debt_policy.yaml").write_text(
        "tickers:\n  DHG:\n    method: cfs_net_borrowing\n    analyst_approved: true\n    publishable: true\n    status: accepted\n    source: analyst\n",
        encoding="utf-8",
    )
    for name in ["wacc_assumptions", "tax_policy", "working_capital_policy"]:
        (tmp_path / f"{name}.yaml").write_text(
            "defaults:\n  status: accepted\n  source: manual\n",
            encoding="utf-8",
        )

    pack = build_valuation_input_pack(
        ticker="DHG",
        run_id="run-1",
        as_of_date=date(2026, 1, 4),
        periods=["2024FY", "2025FY"],
        fact_table=_fact_table(),
        current_price_vnd=93000,
        manual_dir=tmp_path,
    )

    assert pack.market["price"] == 93000
    assert pack.market["shares_outstanding"] == 130746071
    assert pack.peers["peer_ev_ebitda_median"] == 11
    assert pack.debt_policy["method"] == "cfs_net_borrowing"
    assert pack.readiness["fcfe"]["status"] == "ready_with_policy"
    assert pack.readiness["corporate_action"]["corporate_action_status"] == "no_action_recorded"


def test_no_action_recorded_suppresses_share_rollforward_warning():
    result = build_share_rollforward(
        ticker="DHG",
        fact_table={"shares_outstanding.ending": {"2025FY": _entry(130.0)}},
        fy_periods=["2025FY"],
        forecast_labels=["2026F", "2027F"],
        no_action_recorded=True,
    )

    assert result.warnings == []
    assert {row.method for row in result.forecast_rows} == {"no_action_recorded"}


def test_cfs_net_borrowing_policy_makes_fcfe_debt_schedule_publishable():
    forecast = run_forecast(
        ticker="DHG",
        fact_table=_fact_table(),
        forecast_years=[2026, 2027],
        assumptions=ForecastAssumptions(
            debt_policy_method="cfs_net_borrowing",
            debt_schedule_approved=True,
            assumption_status="analyst_approved",
            corporate_action_status="no_action_recorded",
        ),
    )

    assert forecast.debt_schedule is not None
    assert forecast.debt_schedule.forecast_method == "manual_override"
    assert forecast.debt_schedule.is_fcfe_publishable is True
