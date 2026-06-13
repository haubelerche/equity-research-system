"""Adversarial / edge-case tests for analytics and valuation modules.

Each test exercises a boundary condition or invalid-input scenario and asserts
graceful handling: no crash, no NaN/infinity, appropriate None or warning output.

FactEntry objects are constructed directly (not via build_fact_table) to avoid
the unit-validation layer that rejects bare raw_facts without proper fields.
"""
from __future__ import annotations

import math

from backend.facts.normalizer import FactEntry, FactTable


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _entry(value: float) -> FactEntry:
    """Minimal FactEntry with only a value."""
    return FactEntry(value=value, confidence=0.9)


def _table(*items: tuple[str, str, float]) -> FactTable:
    """Build a FactTable from (metric_key, period, value) triples."""
    table: FactTable = {}
    for key, period, value in items:
        table.setdefault(key, {})[period] = _entry(value)
    return table


# ---------------------------------------------------------------------------
# (a) Zero-debt company: FCFE still computes with net_borrowing=0
# ---------------------------------------------------------------------------

def test_zero_debt_fcfe_computes() -> None:
    """A company with no borrowings/debt history must still produce a valid FCFE
    result with net_borrowing=0 for every forecast year (stable leverage policy)."""
    from backend.analytics.forecasting import ForecastAssumptions, run_forecast
    from backend.analytics.fcfe import compute_fcfe, CostOfEquityAssumptions

    # Minimal 3-year history — debt explicitly reported as zero every year.
    # A genuinely debt-free company carries total_debt.ending = 0 facts (the
    # balance-sheet line is reported as 0), which drives the zero_debt_policy
    # path. Absent debt facts would instead be treated as missing data and
    # block FCFE, so the zero values must be explicit.
    table = _table(
        ("revenue.net",        "2022FY", 500.0),
        ("revenue.net",        "2023FY", 550.0),
        ("revenue.net",        "2024FY", 600.0),
        ("gross_profit.total", "2022FY", 200.0),
        ("gross_profit.total", "2023FY", 220.0),
        ("gross_profit.total", "2024FY", 240.0),
        ("net_income.parent",  "2022FY",  50.0),
        ("net_income.parent",  "2023FY",  55.0),
        ("net_income.parent",  "2024FY",  60.0),
        ("total_assets.ending","2024FY", 800.0),
        ("equity.parent",      "2024FY", 700.0),
        ("total_debt.ending",  "2022FY",   0.0),
        ("total_debt.ending",  "2023FY",   0.0),
        ("total_debt.ending",  "2024FY",   0.0),
    )

    forecast = run_forecast(
        ticker="ZEROD",
        fact_table=table,
        forecast_years=[2025, 2026, 2027],
        assumptions=ForecastAssumptions(
            revenue_growth_override=0.08,
            gross_margin_override=0.40,
            capex_to_revenue_override=0.04,
            depreciation_to_revenue_override=0.03,
        ),
        shares_mn=50.0,
    )

    re_assumptions = CostOfEquityAssumptions(re_override=0.12)
    result = compute_fcfe(
        ticker="ZEROD",
        forecast=forecast,
        fact_table=table,
        shares_mn=50.0,
        cost_of_equity_assumptions=re_assumptions,
    )

    # Must not crash; forecast years produced
    assert len(result.forecast_years) == 3

    # Net borrowing must be 0 for every year (no debt → stable leverage policy)
    for fy in result.forecast_years:
        assert fy.net_borrowing == 0.0, (
            f"Expected net_borrowing=0 for {fy.label}, got {fy.net_borrowing}"
        )

    # Equity value must be a finite positive number
    assert result.equity_value is not None
    assert math.isfinite(result.equity_value)
    assert result.equity_value > 0

    # No NaN anywhere in the FCFE table
    for fy in result.forecast_years:
        for attr in ("net_income", "depreciation", "capex", "fcfe", "pv_fcfe"):
            val = getattr(fy, attr)
            if val is not None:
                assert not math.isnan(val), f"{attr} is NaN for {fy.label}"
                assert math.isfinite(val), f"{attr} is infinite for {fy.label}"


# ---------------------------------------------------------------------------
# (b) Missing entire FY: coverage gate status="fail"
# ---------------------------------------------------------------------------

def test_missing_entire_fy_fails_coverage_gate() -> None:
    """A fact table missing 2024FY entirely must return coverage_gate='fail' when
    only 2 FY periods are available (minimum is 3)."""
    from datetime import UTC, datetime
    from backend.facts.completeness import build_fy_validation_report

    # Only 2 FY periods — 2024FY is absent
    table = _table(
        ("revenue.net",         "2022FY", 400.0),
        ("net_income.parent",   "2022FY",  40.0),
        ("total_assets.ending", "2022FY", 600.0),
        ("equity.parent",       "2022FY", 500.0),
        ("operating_cash_flow.total", "2022FY", 45.0),
        ("revenue.net",         "2023FY", 440.0),
        ("net_income.parent",   "2023FY",  44.0),
        ("total_assets.ending", "2023FY", 630.0),
        ("equity.parent",       "2023FY", 520.0),
        ("operating_cash_flow.total", "2023FY", 50.0),
        # 2024FY intentionally absent
    )

    periods_available = ["2022FY", "2023FY"]
    periods_missing = ["2024FY"]

    report = build_fy_validation_report(
        ticker="MISS",
        table=table,
        raw_facts=[],
        required_periods=["2022FY", "2023FY", "2024FY"],
        periods_available=periods_available,
        periods_missing=periods_missing,
        forbidden_periods=[],
        generated_at=datetime.now(UTC),
        validation_status_table={
            key: {p: "accepted" for p in periods_available}
            for key in [
                "revenue.net",
                "net_income.parent",
                "total_assets.ending",
                "equity.parent",
                "operating_cash_flow.total",
            ]
        },
    )

    assert report["coverage_gate"] == "fail", (
        f"Expected coverage_gate='fail', got '{report['coverage_gate']}'"
    )
    assert report["annual_reports_collected"] == 2
    assert report["valuation_ready"] is False
    # Blocking reason must mention insufficient annual reports
    combined_reasons = " ".join(report["blocking_reasons"]).lower()
    assert "insufficient" in combined_reasons or "minimum" in combined_reasons


# ---------------------------------------------------------------------------
# (c) Negative equity: ROE computes gracefully (no crash, warns or returns None)
# ---------------------------------------------------------------------------

def test_negative_equity_roe_no_crash() -> None:
    """A company with negative equity must not crash ROE computation.
    The ratio module must return None (safe_div returns None when denominator=0,
    but equity=-50 is non-zero so safe_div returns a value; we only check no crash
    and no NaN/inf)."""
    from backend.analytics.ratios import compute_ratios

    table = _table(
        ("revenue.net",        "2024FY", 300.0),
        ("net_income.parent",  "2024FY",  10.0),
        ("equity.parent",      "2024FY", -50.0),   # negative equity
        ("total_assets.ending","2024FY", 400.0),
    )

    ratios = compute_ratios(table)

    # Must not crash; ROE may be present or absent but must not be NaN/inf
    roe = ratios.get("roe", {}).get("2024FY")
    if roe is not None:
        assert not math.isnan(roe), "ROE is NaN for negative-equity company"
        assert math.isfinite(roe), "ROE is infinite for negative-equity company"
    # ROA should still be computable (assets are positive)
    roa = ratios.get("roa", {}).get("2024FY")
    assert roa is not None, "ROA should be computable when assets > 0"
    assert not math.isnan(roa)


def test_zero_equity_roe_returns_none() -> None:
    """equity.parent = 0 must return ROE = None (safe_div guards against
    division by zero)."""
    from backend.analytics.ratios import compute_ratios

    table = _table(
        ("revenue.net",        "2024FY", 300.0),
        ("net_income.parent",  "2024FY",  10.0),
        ("equity.parent",      "2024FY",   0.0),   # zero equity
        ("total_assets.ending","2024FY", 400.0),
    )

    ratios = compute_ratios(table)

    # _safe_div(num, 0.0) must return None — never raises ZeroDivisionError
    roe = ratios.get("roe", {}).get("2024FY")
    assert roe is None, f"Expected ROE=None for zero equity, got {roe}"


# ---------------------------------------------------------------------------
# (d) Zero revenue: margins are None, not infinity or NaN
# ---------------------------------------------------------------------------

def test_zero_revenue_margins_are_none() -> None:
    """revenue.net = 0 for a period must produce None for all margin metrics,
    never infinity or NaN."""
    from backend.analytics.ratios import compute_ratios

    table = _table(
        ("revenue.net",        "2024FY",   0.0),   # zero revenue
        ("gross_profit.total", "2024FY",  50.0),
        ("net_income.parent",  "2024FY",  10.0),
        ("ebitda.total",       "2024FY",  20.0),
        ("equity.parent",      "2024FY", 200.0),
        ("total_assets.ending","2024FY", 400.0),
    )

    ratios = compute_ratios(table)

    for margin_key in ("gross_margin", "net_margin", "ebitda_margin", "ebit_margin"):
        value = ratios.get(margin_key, {}).get("2024FY")
        assert value is None, (
            f"Expected {margin_key}=None for zero revenue, got {value}"
        )
    # Sanity: values that do NOT require revenue must still work
    roe = ratios.get("roe", {}).get("2024FY")
    if roe is not None:
        assert math.isfinite(roe)


# ---------------------------------------------------------------------------
# (e) Extreme forecast horizon: 20-year forecast must not crash
# ---------------------------------------------------------------------------

def test_extreme_forecast_horizon_no_crash() -> None:
    """A 20-year forecast horizon must complete without error and produce
    the expected number of forecast year objects."""
    from backend.analytics.forecasting import ForecastAssumptions, run_forecast

    table = _table(
        ("revenue.net",        "2022FY", 1000.0),
        ("revenue.net",        "2023FY", 1080.0),
        ("revenue.net",        "2024FY", 1166.0),
        ("gross_profit.total", "2022FY",  400.0),
        ("gross_profit.total", "2023FY",  432.0),
        ("gross_profit.total", "2024FY",  466.0),
        ("net_income.parent",  "2022FY",  100.0),
        ("net_income.parent",  "2023FY",  108.0),
        ("net_income.parent",  "2024FY",  116.0),
        ("total_assets.ending","2024FY", 2000.0),
        ("equity.parent",      "2024FY", 1500.0),
    )

    horizon = list(range(2025, 2025 + 20))  # 20 years

    result = run_forecast(
        ticker="LONG",
        fact_table=table,
        forecast_years=horizon,
        assumptions=ForecastAssumptions(
            revenue_growth_override=0.06,
            gross_margin_override=0.40,
            capex_to_revenue_override=0.03,
            depreciation_to_revenue_override=0.03,
        ),
        shares_mn=100.0,
    )

    # Must not crash and must produce exactly 20 forecast year objects
    assert len(result.forecast_years) == 20, (
        f"Expected 20 forecast years, got {len(result.forecast_years)}"
    )

    # All revenues must be positive finite floats (no NaN, no inf)
    for fy in result.forecast_years:
        assert fy.revenue is not None, f"revenue is None for {fy.label}"
        assert math.isfinite(fy.revenue), f"revenue is not finite for {fy.label}"
        assert fy.revenue > 0, f"revenue is non-positive for {fy.label}"

    # Net income must be finite for all years
    for fy in result.forecast_years:
        if fy.net_income is not None:
            assert math.isfinite(fy.net_income), f"net_income not finite for {fy.label}"

    # Forecast labels must follow the expected pattern
    expected_labels = [f"{y}F" for y in horizon]
    actual_labels = [fy.label for fy in result.forecast_years]
    assert actual_labels == expected_labels


def test_extreme_forecast_with_fcfe_no_crash() -> None:
    """FCFE over a 20-year horizon must complete without crash and produce
    a finite equity value."""
    from backend.analytics.forecasting import ForecastAssumptions, run_forecast
    from backend.analytics.fcfe import compute_fcfe, CostOfEquityAssumptions

    table = _table(
        ("revenue.net",        "2022FY", 1000.0),
        ("revenue.net",        "2023FY", 1050.0),
        ("revenue.net",        "2024FY", 1100.0),
        ("gross_profit.total", "2022FY",  400.0),
        ("gross_profit.total", "2023FY",  420.0),
        ("gross_profit.total", "2024FY",  440.0),
        ("net_income.parent",  "2022FY",   80.0),
        ("net_income.parent",  "2023FY",   84.0),
        ("net_income.parent",  "2024FY",   88.0),
        ("total_assets.ending","2024FY", 1500.0),
        ("equity.parent",      "2024FY", 1200.0),
        ("total_debt.ending",  "2022FY",    0.0),
        ("total_debt.ending",  "2023FY",    0.0),
        ("total_debt.ending",  "2024FY",    0.0),
    )

    horizon = list(range(2025, 2025 + 20))
    forecast = run_forecast(
        ticker="LONGFCFE",
        fact_table=table,
        forecast_years=horizon,
        assumptions=ForecastAssumptions(
            revenue_growth_override=0.05,
            gross_margin_override=0.40,
            capex_to_revenue_override=0.03,
            depreciation_to_revenue_override=0.03,
        ),
        shares_mn=80.0,
    )

    result = compute_fcfe(
        ticker="LONGFCFE",
        forecast=forecast,
        fact_table=table,
        shares_mn=80.0,
        cost_of_equity_assumptions=CostOfEquityAssumptions(re_override=0.12),
    )

    assert len(result.forecast_years) == 20
    assert math.isfinite(result.equity_value)
    assert result.equity_value > 0


# ---------------------------------------------------------------------------
# (f) Rendered HTML must not expose internal system terms
# ---------------------------------------------------------------------------

def test_rendered_html_no_internal_jargon(tmp_path) -> None:
    """Rendered report HTML must not contain internal implementation terms that
    would expose backend internals to end users."""
    from backend.reporting.section_builder import ReportContext, build_report_sections
    from backend.reporting.html_renderer import HTMLRenderer

    ctx = ReportContext(
        ticker="DBD",
        company_name="Duoc Binh Dinh",
        exchange="HSX",
        report_date="2026-06-07",
        data_cutoff="2025-12-31",
        rating="BUY",
        current_price=38000,
        target_price=45000,
        upside_pct=18.4,
        risk_level="Trung bình",
        data_confidence="Cao",
        status="APPROVED",
    )

    sections = build_report_sections(ctx)
    out_path = HTMLRenderer().render(sections, ctx, output_dir=tmp_path)

    html = out_path.read_text(encoding="utf-8")

    # None of these internal terms must appear in the exported HTML
    forbidden_terms = [
        "needs_review",
        "source_tier",
        "Tier-3",
        "gate_failed",
        "chunk_id",
        "parser",
    ]

    found_violations: list[str] = []
    for term in forbidden_terms:
        if term.lower() in html.lower():
            found_violations.append(term)

    assert not found_violations, (
        f"Rendered HTML contains internal jargon terms: {found_violations}. "
        "These must not appear in client-facing output."
    )
