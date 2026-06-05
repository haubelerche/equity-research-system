"""Regression tests for period-suffix normalisation in client_report_view_model."""
from __future__ import annotations

import json

import pytest

from backend.reporting.client_report_view_model import _derive_dividend_per_share


class TestDeriveDividendPerShare:
    """Item 37: _derive_dividend_per_share must not crash on dict/null/scalar inputs."""

    def test_scalar_value_returned(self):
        facts = {"dividends_per_share.cash": {"2025FY": 2000.0}}
        assert _derive_dividend_per_share(facts, ["2025FY"]) == 2000.0

    def test_dict_factentry_value_extracted(self):
        facts = {"dividends_per_share.cash": {"2025FY": {"value": 2000.0, "unit": "VND"}}}
        assert _derive_dividend_per_share(facts, ["2025FY"]) == 2000.0

    def test_none_value_returns_none(self):
        facts = {"dividends_per_share.cash": {"2025FY": None}}
        assert _derive_dividend_per_share(facts, ["2025FY"]) is None

    def test_missing_key_returns_none(self):
        facts: dict = {}
        assert _derive_dividend_per_share(facts, ["2025FY"]) is None

    def test_zero_value_skipped(self):
        facts = {"dividends_per_share.cash": {"2024FY": 0.0, "2025FY": 1500.0}}
        assert _derive_dividend_per_share(facts, ["2024FY", "2025FY"]) == 1500.0

    def test_dict_with_none_value_returns_none(self):
        facts = {"dividends_per_share.cash": {"2025FY": {"value": None}}}
        assert _derive_dividend_per_share(facts, ["2025FY"]) is None

    def test_latest_period_preferred(self):
        facts = {"dividends_per_share.cash": {"2023FY": 1000.0, "2025FY": 2000.0}}
        assert _derive_dividend_per_share(facts, ["2023FY", "2024FY", "2025FY"]) == 2000.0


def test_to_fact_period_normalizes_a_suffix():
    """Period key helper must convert 'A'-suffix display labels to 'FY' canonical keys."""
    from backend.reporting.client_report_view_model import _to_fact_period, _is_actual

    assert _to_fact_period("2024A") == "2024FY"
    assert _to_fact_period("2024FY") == "2024FY"
    assert _to_fact_period("2022A") == "2022FY"
    assert _is_actual("2024A") is True
    assert _is_actual("2024FY") is True
    assert _is_actual("2026F") is False


def _write_fy_suffix_fixture(tmp_path, monkeypatch, ticker: str = "DHG") -> str:
    """Write minimal fact/valuation artifacts using FY-suffix keys and return run_id."""
    from backend.reporting.artifact_manifest import ArtifactManifest, write_manifest

    artifacts = tmp_path / "artifacts"
    facts_dir = artifacts / "facts"
    valuation_dir = artifacts / "valuation"
    facts_dir.mkdir(parents=True)
    valuation_dir.mkdir(parents=True)

    facts_path = facts_dir / f"{ticker}_facts.json"
    facts_path.write_text(
        json.dumps({
            "facts": {
                "revenue.net": {
                    "2023FY": 4_500_000_000_000.0,
                    "2024FY": 5_000_000_000_000.0,
                },
                "gross_profit.total": {
                    "2023FY": 2_000_000_000_000.0,
                    "2024FY": 2_200_000_000_000.0,
                },
                "net_income.parent": {
                    "2023FY": 450_000_000_000.0,
                    "2024FY": 500_000_000_000.0,
                },
                "cogs.total": {"2023FY": -2_500_000_000_000.0, "2024FY": -2_800_000_000_000.0},
                "depreciation.total": {"2023FY": 50_000_000_000.0, "2024FY": 55_000_000_000.0},
                "sga.total": {"2023FY": -1_200_000_000_000.0, "2024FY": -1_300_000_000_000.0},
                "interest_expense.total": {"2023FY": -10_000_000_000.0, "2024FY": -12_000_000_000.0},
                "tax_expense.total": {"2023FY": -80_000_000_000.0, "2024FY": -90_000_000_000.0},
                "operating_cash_flow.total": {"2023FY": 500_000_000_000.0, "2024FY": 550_000_000_000.0},
                "capex.total": {"2023FY": -150_000_000_000.0, "2024FY": -160_000_000_000.0},
                "free_cash_flow.total": {"2023FY": 350_000_000_000.0, "2024FY": 390_000_000_000.0},
                "equity.parent": {"2023FY": 2_000_000_000_000.0, "2024FY": 2_200_000_000_000.0},
                "total_assets.ending": {"2023FY": 3_500_000_000_000.0, "2024FY": 3_800_000_000_000.0},
                "cash_and_equivalents.ending": {"2023FY": 300_000_000_000.0, "2024FY": 350_000_000_000.0},
                "short_term_debt.ending": {"2023FY": 100_000_000_000.0, "2024FY": 110_000_000_000.0},
                "eps.basic": {"2023FY": 4500.0, "2024FY": 5000.0},
                "shares_outstanding.total": {"2024FY": 94_000_000.0},
            }
        }),
        encoding="utf-8",
    )

    valuation_path = valuation_dir / f"{ticker}_valuation.json"
    valuation_path.write_text(
        json.dumps({
            "forecast": {
                "drivers": {
                    "revenue_growth": {"value": 0.08},
                    "gross_margin": {"value": 0.44},
                    "sga_to_revenue": {"value": 0.26},
                    "depreciation_to_revenue": {"value": 0.01},
                    "capex_to_revenue": {"value": 0.03},
                    "effective_tax_rate": {"value": 0.158},
                },
                "forecast_years": [
                    {
                        "label": "2025F",
                        "revenue": 5_400_000_000_000.0,
                        "cogs": -3_024_000_000_000.0,
                        "gross_profit": 2_376_000_000_000.0,
                        "depreciation": 54_000_000_000.0,
                        "sga": -1_404_000_000_000.0,
                        "interest_expense": -13_000_000_000.0,
                        "tax_expense": -92_000_000_000.0,
                        "net_income": 540_000_000_000.0,
                        "capex": -162_000_000_000.0,
                        "equity": 2_400_000_000_000.0,
                        "total_assets": 4_000_000_000_000.0,
                        "total_debt": 120_000_000_000.0,
                        "eps": 5740.0,
                        "ebit": 918_000_000_000.0,
                        "profit_before_tax": 905_000_000_000.0,
                        "bvps": 25531.0,
                    }
                ],
            },
            "fcff": {
                "wacc": 0.12,
                "terminal_growth": 0.03,
                "wacc_breakdown": {"tax_rate": 0.158, "cost_of_equity": 0.138},
                "fcff_table": [{"label": "2025F", "fcff": 400_000_000_000.0, "delta_nwc": -30_000_000_000.0}],
            },
            "blend_dcf": {
                "current_price_vnd": 95000.0,
                "target_price_dcf_vnd": 118000.0,
                "upside_pct": 0.24,
            },
        }),
        encoding="utf-8",
    )

    run_id = "run_fy_suffix_regression"
    manifest = ArtifactManifest(
        run_id=run_id,
        ticker=ticker,
        created_at="2026-06-03T00:00:00",
        schema_version=1,
        artifacts={
            "facts": {"path": str(facts_path), "producer": "TEST"},
            "valuation": {"path": str(valuation_path), "producer": "TEST"},
        },
    )
    write_manifest(manifest, base_dir=artifacts)
    monkeypatch.setattr("backend.reporting.client_report_view_model.ROOT", tmp_path)
    return run_id


def test_derive_periods_includes_forecast_years(tmp_path, monkeypatch):
    """Periods must include forecast (F) years from the forecast artifact, not only actuals.

    Regression for the dropped-forecast-columns bug: _derive_periods previously kept
    only periods ending in 'FY'/'A', silently discarding 2026F..2030F so the financial
    tables never showed any forecast column even when the forecast engine produced them.
    """
    from backend.reporting.client_report_view_model import build_client_report_view_model

    run_id = _write_fy_suffix_fixture(tmp_path, monkeypatch, ticker="DHG")
    vm = build_client_report_view_model("DHG", "analyst_draft", run_id=run_id)

    periods = vm.financial_summary_table.periods
    assert any(p.endswith("F") for p in periods), (
        f"No forecast (F) period in table headers: {periods} — forecast columns dropped"
    )
    assert "2025F" in periods, f"Forecast year 2025F missing from periods: {periods}"
    # Actuals must still be present and ordered before forecasts
    assert any(p.startswith("2024") for p in periods), f"Actual 2024 missing: {periods}"
    f_index = next(i for i, p in enumerate(periods) if p.endswith("F"))
    assert all(not p.endswith("F") for p in periods[:f_index]), (
        f"Actual periods must precede forecast periods: {periods}"
    )


def test_shares_missing_with_eps_present_flags_missing_field(tmp_path, monkeypatch):
    """EPS present but no share count must add 'shares_outstanding' to missing fields.

    PLAN §1.9 / §4.3: a populated EPS row with shares=0 is a critical inconsistency that
    must block client-final export rather than silently rendering.
    """
    import backend.reporting.client_report_view_model as vm_mod
    from backend.reporting.client_report_view_model import build_client_report_view_model

    run_id = _write_fy_suffix_fixture(tmp_path, monkeypatch, ticker="DHG")
    # No market snapshot under the temp ROOT -> shares cannot be sourced; fixture facts
    # use shares_outstanding.total only for 2024FY, EPS exists for 2023FY/2024FY.
    monkeypatch.setattr(vm_mod, "_derive_shares_mn", lambda *a, **k: 0.0)

    vm = build_client_report_view_model("DHG", "analyst_draft", run_id=run_id)
    assert "shares_outstanding" in vm.missing_required_fields


def test_build_vm_table_uses_fy_suffix_keys(tmp_path, monkeypatch):
    """TableData must show real values when facts are stored under 'FY'-suffix keys.

    This is the key regression: if _to_fact_period is not applied consistently,
    facts stored as '2024FY' keys will not be found when the display period is '2024A',
    resulting in all-zero / all-dash revenue rows.
    """
    from backend.reporting.client_report_view_model import build_client_report_view_model

    run_id = _write_fy_suffix_fixture(tmp_path, monkeypatch, ticker="DHG")
    vm = build_client_report_view_model("DHG", "analyst_draft", run_id=run_id)

    # The income statement (financial_summary_table) must have real (non-zero) revenue rows
    income_rows = {row[0]: row[1] for row in vm.financial_summary_table.rows}

    revenue_row = income_rows.get("Doanh thu thuần") or income_rows.get("Revenue")
    assert revenue_row is not None, "Revenue row missing from financial_summary_table"
    assert any(v not in (None, 0, "—") for v in revenue_row), (
        "Revenue row is all zeros/dashes — FY-suffix fact keys not being resolved"
    )

    # Net income row must also have real values
    net_income_row = income_rows.get("Lợi nhuận ròng") or income_rows.get("Net Income")
    assert net_income_row is not None, "Net income row missing from financial_summary_table"
    assert any(v not in (None, 0, "—") for v in net_income_row), (
        "Net income row is all zeros/dashes — FY-suffix fact keys not being resolved"
    )


def test_sensitivity_matrix_from_artifact():
    """_table_sensitivity_matrix renders a WACC x g target-price grid; None when all-null."""
    from backend.reporting.client_report_view_model import _table_sensitivity_matrix

    sens = {
        "fcff_wacc_g": {
            "wacc_range": [0.10, 0.12],
            "g_range": [0.02, 0.03],
            "matrix": {
                "0.100": {"0.02": 49323.0, "0.03": 54439.0},
                "0.120": {"0.02": 39679.0, "0.03": 42641.0},
            },
        }
    }
    table = _table_sensitivity_matrix(sens)
    assert table is not None
    assert table.periods == ["g=2.0%", "g=3.0%"]
    row_map = {r[0]: r[1] for r in table.rows}
    assert row_map["WACC 12.0%"] == [39679.0, 42641.0]
    assert table.format_type == "currency"
    from backend.reporting.client_section_builder import _render_table
    html = _render_table(table)
    assert "39,679" in html
    assert "3,967,900.0%" not in html
    # No "—" / None cells in a populated matrix
    assert all(v is not None for _, vals in table.rows for v in vals)

    # All-null matrix -> None (caller falls back to scenario view)
    null_sens = {"fcff_wacc_g": {"wacc_range": [0.1], "g_range": [0.03], "matrix": {"0.100": {"0.03": None}}}}
    assert _table_sensitivity_matrix(null_sens) is None
    assert _table_sensitivity_matrix({}) is None


def test_analyst_draft_shows_computed_values_when_not_publishable(tmp_path, monkeypatch):
    """analyst_draft always shows computed target/upside/recommendation even when not officially publishable."""
    from backend.reporting.artifact_manifest import ArtifactManifest, write_manifest
    from backend.reporting.client_report_view_model import build_client_report_view_model

    ticker = "DBD"
    artifacts = tmp_path / "artifacts"
    facts_dir = artifacts / "facts"
    val_dir = artifacts / "valuation"
    result_dir = artifacts / "valuation_results"
    facts_dir.mkdir(parents=True)
    val_dir.mkdir(parents=True)
    result_dir.mkdir(parents=True)

    facts_path = facts_dir / f"{ticker}_facts.json"
    facts_path.write_text(
        json.dumps({"facts": {"revenue.net": {"2025FY": 1000.0}, "eps.basic": {"2025FY": 1000.0}}}),
        encoding="utf-8",
    )
    valuation_path = val_dir / f"{ticker}_valuation.json"
    valuation_path.write_text(
        json.dumps({
            "forecast": {"forecast_years": [{"label": "2026F", "revenue": 1100.0}]},
            "fcff": {"wacc": 0.138, "terminal_growth": 0.03, "fcff_table": [{"label": "2026F", "fcff": 100.0}]},
            "blend_dcf": {
                "current_price_vnd": 50200.0,
                "target_price_dcf_vnd": 30409.0,
                "upside_pct": -0.3942,
                "valuation_gap_pct": 0.599,
                "is_draft_only": True,
            },
        }),
        encoding="utf-8",
    )
    result_path = result_dir / f"run_{ticker}_valuation_result.json"
    result_path.write_text(
        json.dumps({
            "ticker": ticker,
            "current_price": 50200.0,
            "target_price": 30409.0,
            "upside_downside": -0.3942,
            "rating_model_output": "BÁN",
            "is_publishable": False,
        }),
        encoding="utf-8",
    )
    manifest = ArtifactManifest(
        run_id="run_gate_test",
        ticker=ticker,
        created_at="2026-06-03T00:00:00",
        schema_version=1,
        artifacts={
            "facts": {"path": str(facts_path), "producer": "TEST"},
            "valuation": {"path": str(valuation_path), "producer": "TEST"},
            "valuation_result": {"path": str(result_path), "producer": "TEST"},
        },
    )
    write_manifest(manifest, base_dir=artifacts)
    monkeypatch.setattr("backend.reporting.client_report_view_model.ROOT", tmp_path)

    vm = build_client_report_view_model(ticker, "analyst_draft", run_id="run_gate_test")

    # analyst_draft always shows computed values — blocking reasons are informational only
    assert vm.recommendation == "BÁN"  # upside=-0.3942 < -0.20
    assert vm.target_price is not None
    assert vm.upside_downside is not None
    assert vm.display_blocking_reasons == []


def test_non_valuation_narrative_sanitizer_removes_valuation_sentences():
    from backend.reporting.client_report_view_model import _sanitize_non_valuation_narrative

    text = (
        "Doanh nghiệp vận hành mô hình kinh doanh dược phẩm ổn định. "
        "Về định giá, WACC và target price làm thay đổi giá mục tiêu."
    )

    cleaned = _sanitize_non_valuation_narrative(text)

    assert "mô hình kinh doanh" in cleaned
    assert "target price" not in cleaned.lower()
    assert "wacc" not in cleaned.lower()
    assert "định giá" not in cleaned.lower()


def test_total_return_adds_dividend_yield():
    from backend.reporting.client_report_view_model import _total_return, Percent
    assert abs(_total_return(-0.394, Percent(0.0398)).value - (-0.3542)) < 1e-9
    assert _total_return(0.12, None).value == 0.12
    assert _total_return(None, Percent(0.04)) is None


class TestReportDisplayGovernance:
    """Regression guard: analyst_draft must not blank target_price when is_publishable=False."""

    _val_result_blocked = {"is_publishable": False, "current_price": 50200, "target_price": 27444}
    _blend_draft = {
        "is_draft_only": True,
        "current_price_vnd": 50200.0,
        "target_price_dcf_vnd": 27444.0,
        "upside_pct": -0.453,
        "valuation_gap_pct": 0.45,
    }

    def test_analyst_draft_shows_target_price_when_not_publishable(self):
        from backend.reporting.client_report_view_model import _report_display_governance
        result = _report_display_governance("analyst_draft", self._val_result_blocked, self._blend_draft)
        assert result["target_price"] == 27444.0, (
            "analyst_draft must show computed target price even when is_publishable=False"
        )
        assert result["approved_for_display"] is True
        assert result["recommendation"] == "BÁN"
        assert result["blocking_reasons"] == []

    def test_client_final_blocks_target_price_when_not_publishable(self):
        from backend.reporting.client_report_view_model import _report_display_governance
        result = _report_display_governance("client_final", self._val_result_blocked, self._blend_draft)
        assert result["target_price"] is None, (
            "client_final must block target_price when is_publishable=False"
        )
        assert result["approved_for_display"] is False
        assert "valuation_result_not_publishable" in result["blocking_reasons"]
