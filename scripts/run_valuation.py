# DEV-ONLY — production runs use run_research.py
"""Phase 4 — Code-First Valuation.

Reads from a research snapshot (frozen accepted facts), runs deterministic
ratio analysis, DCF (3 scenarios), multiples, and sensitivity table.
Saves a structured valuation artifact.

Usage:
    python scripts/run_valuation.py --ticker DHG
    python scripts/run_valuation.py --ticker DHG --wacc 0.10 --terminal-growth 0.03
    python scripts/run_valuation.py --ticker DHG --target-pe 18 --target-ev-ebitda 12

Outputs:
    storage/runs/{run_id}/valuation.json
    stdout: ratio table + valuation summary
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import replace as _dc_replace
from datetime import UTC, datetime
from pathlib import Path

# Reconfigure stdout to UTF-8 so Vietnamese warning strings don't crash on cp1252 consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
if "" in sys.path:
    sys.path = [p for p in sys.path if p != ""] + [""]

from backend.period_scope import DEFAULT_FROM_YEAR, DEFAULT_TO_YEAR

_env_file = Path(__file__).resolve().parents[1] / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip(chr(34)).strip(chr(39)))

ROOT = Path(__file__).resolve().parents[1]
VALUATION_DIR = ROOT / "storage" / "runs" / os.environ.get("RUN_ID", "missing_run_id")

def _get_current_price(ticker: str) -> float | None:
    """Fetch latest close price from fact.price_history."""
    try:
        from backend.database.fact_store import PostgresFactStore
        store = PostgresFactStore()
        from datetime import timedelta
        end = datetime.now(UTC).date()
        start = end - timedelta(days=30)
        df = store.get_price_history(ticker=ticker, start=str(start), end=str(end))
        if df is not None and not df.empty:
            latest = df.sort_values("trade_date").iloc[-1]
            price = float(latest.get("adjusted_close") or latest.get("close") or 0)
            if price > 0:
                # vnstock stores prices in thousands VND; convert to VND/share
                return price * 1000
    except Exception as exc:  # noqa: BLE001
        print(f"[run_valuation] WARNING: could not fetch price for {ticker}: {exc}")
    return None


def _print_wacc_g_matrix(
    matrix: dict,
    g_range: list[float],
    title: str,
    row_label: str = "WACC",
) -> None:
    print(f"\n  {title} — {row_label} rows x terminal-growth cols")
    print(f"  {row_label:<10} " + "  ".join(f"{g:.1%}".rjust(9) for g in g_range))
    print(f"  {'-' * (12 + 11 * len(g_range))}")
    for w_key, g_vals in matrix.items():
        label = f"{float(w_key):.1%}"
        row = []
        for g in g_range:
            g_key = f"{g:.4f}".rstrip("0").rstrip(".")
            v = g_vals.get(g_key)
            row.append(f"{v:>9,.0f}" if v is not None else "        —")
        print(f"  {label:<10} " + "  ".join(row))


def _print_fcf_summary(label: str, d: dict, tv_check: dict) -> None:
    print(f"  {label} target price: {d.get('target_price_vnd') or 'N/A'}", end="")
    if d.get("target_price_vnd"):
        print(f"  ({d['target_price_vnd']:,.0f} VND/share)", end="")
    print()
    if d.get("upside_pct") is not None:
        print(f"  {label} upside:       {d['upside_pct']:.2%}")
    if d.get("enterprise_value") or d.get("equity_value"):
        ev = d.get("enterprise_value") or d.get("equity_value")
        print(f"  {label} EV/Eq Value:  {ev:,.1f} VND bn")
    tv_status = tv_check.get("status", "unknown")
    tv_w = tv_check.get("tv_weight")
    tv_str = f"{tv_w:.1%}" if tv_w is not None else "N/A"
    print(f"  {label} TV weight:    {tv_str} [{tv_status}]")
    if tv_check.get("warning"):
        print(f"  WARN (TV): {tv_check['warning']}")


def _print_blend_grid(grid: dict) -> None:
    p_fcff_range = grid.get("price_fcff_range", [])
    p_fcfe_range = grid.get("price_fcfe_range", [])
    if not p_fcff_range or not p_fcfe_range:
        return
    print(f"  {'FCFF \\ FCFE':<12} " + "  ".join(f"{p:>9,.0f}" for p in p_fcfe_range))
    print(f"  {'-' * (14 + 11 * len(p_fcfe_range))}")
    matrix = grid.get("matrix", {})
    for p_fcff in p_fcff_range:
        row_key = str(int(round(p_fcff)))
        row_data = matrix.get(row_key, {})
        row = []
        for p_fcfe in p_fcfe_range:
            col_key = str(int(round(p_fcfe)))
            v = row_data.get(col_key)
            row.append(f"{v:>9,.0f}" if v is not None else "        —")
        print(f"  {p_fcff:>10,.0f}   " + "  ".join(row))
    upside = grid.get("upside_range", {})
    if upside:
        print(f"  Upside range: [{upside.get('min_upside', 0):.1%}, {upside.get('max_upside', 0):.1%}]")


def _print_pe_grid(pe_sens: dict, current_price: float | None) -> None:
    eps_range = pe_sens.get("eps_range", [])
    pe_range  = pe_sens.get("pe_range", [])
    if not eps_range or not pe_range:
        return
    print(f"  {'EPS \\ P/E':<12} " + "  ".join(f"{pe:>9}x" for pe in pe_range))
    print(f"  {'-' * (14 + 11 * len(pe_range))}")
    matrix = pe_sens.get("matrix", {})
    for eps in eps_range:
        eps_key = str(int(round(eps)))
        row_data = matrix.get(eps_key, {})
        row = []
        for pe in pe_range:
            cell = row_data.get(str(pe), {})
            price = cell.get("price") if isinstance(cell, dict) else None
            row.append(f"{price:>9,.0f}" if price is not None else "        —")
        print(f"  {eps:>10,.0f}   " + "  ".join(row))


def _print_ev_grid(ev_sens: dict, current_price: float | None) -> None:
    ebitda_range = ev_sens.get("ebitda_range", [])
    mult_range   = ev_sens.get("multiple_range", [])
    if not ebitda_range or not mult_range:
        return
    print(f"  {'EBITDA \\ x':<12} " + "  ".join(f"{m:>9.1f}x" for m in mult_range))
    print(f"  {'-' * (14 + 11 * len(mult_range))}")
    matrix = ev_sens.get("matrix", {})
    for ebitda in ebitda_range:
        ebitda_key = str(int(round(ebitda)))
        row_data = matrix.get(ebitda_key, {})
        row = []
        for m in mult_range:
            cell = row_data.get(str(m), {})
            price = cell.get("price") if isinstance(cell, dict) else None
            row.append(f"{price:>9,.0f}" if price is not None else "        —")
        print(f"  {ebitda:>10.0f}   " + "  ".join(row))


def _formula_trace(
    trace_id: str,
    formula_id: str,
    formula_version: str,
    output_name: str,
    output_value,
    unit: str | None,
    period: str | None,
    input_values: dict,
    calculation_steps: list[dict],
    input_fact_ids: list | None = None,
    warnings: list[str] | None = None,
) -> dict:
    return {
        "trace_id": trace_id,
        "formula_id": formula_id,
        "formula_version": formula_version,
        "output_name": output_name,
        "output_value": output_value,
        "unit": unit,
        "period": period,
        "input_fact_ids": input_fact_ids or [],
        "input_values": input_values,
        "calculation_steps": calculation_steps,
        "warnings": warnings or [],
    }


def _fact_ids(raw_facts: list[dict], metrics: list[str], periods: list[str] | None = None) -> list:
    wanted_periods = set(periods or [])
    ids = []
    for fact in raw_facts:
        metric = fact.get("line_item_code")
        period = f"{fact.get('fiscal_year')}FY" if fact.get("fiscal_year") else None
        if metric in metrics and (not wanted_periods or period in wanted_periods):
            ids.append(fact.get("id") or fact.get("fact_id") or f"{metric}:{period}")
    return ids


def run_valuation(
    ticker: str,
    from_year: int = DEFAULT_FROM_YEAR,
    to_year: int = DEFAULT_TO_YEAR,
    wacc: float = 0.10,
    terminal_growth: float = 0.03,
    forecast_years: int = 5,
    target_pe: float = 15.0,
    target_pb: float = 2.5,
    target_ev_ebitda: float = 10.0,
    auto_approve_assumptions: bool = False,
) -> dict:
    from backend.dataops.snapshot import create_snapshot, load_snapshot_facts
    from backend.facts.normalizer import (
        build_fact_table,
        compute_derived,
        periods_sorted,
        to_analytics_vnd_bn,
    )
    from backend.analytics.ratios import compute_ratios, ratio_table_for_display
    from backend.analytics.dcf import DCFAssumptions, run_three_scenarios
    from backend.analytics.multiples import compute_multiples
    from backend.analytics.forecasting import run_forecast, ForecastAssumptions
    from backend.analytics.fcff import WACCAssumptions, compute_fcff
    from backend.analytics.fcfe import CostOfEquityAssumptions, compute_fcfe
    from backend.analytics.blend import blend_dcf
    from backend.analytics.sensitivity import (
        build_sensitivity_table,
        build_fcff_sensitivity_table,
        build_fcfe_sensitivity_table,
        build_blend_sensitivity_table,
        build_pe_sensitivity_table,
        build_ev_ebitda_sensitivity_table,
        compute_tv_weight,
        compute_valuation_gap,
    )
    from backend.analytics.approval_gate import build_gate_from_artifacts
    from backend.analytics.valuation_confidence import build_valuation_confidence
    from backend.analytics.core_pe_net_cash import compute_core_pe_net_cash

    ticker = ticker.strip().upper()
    generated_at = datetime.now(UTC)
    assumption_status = "analyst_approved" if auto_approve_assumptions else "default_unapproved"

    print(f"[run_valuation] {ticker} — creating/loading research snapshot")
    snap = create_snapshot(ticker=ticker, from_year=from_year, to_year=to_year, created_by="run_valuation")
    snapshot_id = snap["snapshot_id"]
    print(f"[run_valuation] {ticker} snapshot: {snapshot_id} ({snap['facts_count']} facts, periods={snap['periods']})")

    if snap["facts_count"] == 0:
        print(f"[run_valuation] ERROR: No accepted facts in snapshot. Run build_facts.py first.")
        sys.exit(1)

    print(f"[run_valuation] {ticker} — loading facts from snapshot")
    raw_facts = load_snapshot_facts(snapshot_id)
    print(f"[run_valuation] {ticker} — {len(raw_facts)} facts loaded from snapshot")

    # Supplement snapshot with golden CSV facts (audited values not yet in DB).
    # Tier-based conflict resolution in build_fact_table() ensures golden CSV
    # tier-0 facts override lower-tier API facts for the same key/period.
    from backend.facts.normalizer import load_golden_csv_supplement
    _golden_suppl = load_golden_csv_supplement(ticker, from_year=from_year, to_year=to_year)
    if _golden_suppl:
        raw_facts = raw_facts + _golden_suppl
        print(f"[run_valuation] {ticker} — supplemented with {len(_golden_suppl)} golden CSV facts")

    base_table = to_analytics_vnd_bn(build_fact_table(raw_facts))
    full_table = compute_derived(base_table)
    fy_periods = sorted(p for p in periods_sorted(full_table) if p.endswith("FY"))

    print(f"[run_valuation] {ticker} FY periods: {fy_periods}")

    # ── Phase 02/06: inject market-source shares_outstanding ──────────────────
    # Shares outstanding is a market-source canonical fact (not a statement line item),
    # absent from snapshot facts. Without it FCFF/FCFE block the target price AND the
    # WACC×g / Re×g sensitivity matrices come back all-null. Source it from the vnstock
    # VCI overview (MarketSnapshot) with provenance.
    if fy_periods and "shares_outstanding.ending" not in full_table:
        try:
            from backend.reporting.market_snapshot import get_market_snapshot
            from backend.facts.normalizer import FactEntry
            _snap = get_market_snapshot(ticker)
            _shares = _snap.shares_outstanding_fact() if _snap else None
            if _shares:
                full_table["shares_outstanding.ending"] = {
                    fy_periods[-1]: FactEntry(
                        value=_shares,
                        source_id=_snap.source,
                        source_title="vnstock VCI overview (issue_share)",
                        confidence=0.9,
                    )
                }
                print(f"[run_valuation] {ticker} — injected shares_outstanding.ending={_shares:,.0f}")
        except Exception as _exc:  # noqa: BLE001 - non-fatal; valuation will block target instead
            print(f"[run_valuation] WARNING: shares injection failed ({_exc})")

    # ── Ratio analysis ────────────────────────────────────────────────────────
    print(f"\n[run_valuation] {ticker} — computing ratios")
    ratios = compute_ratios(full_table)
    ratio_display = ratio_table_for_display(ratios, fy_periods)

    _RATIO_ORDER = [
        "revenue_growth", "gross_margin", "ebitda_margin", "net_margin",
        "roe", "roa", "current_ratio", "quick_ratio",
        "debt_to_equity", "net_debt_to_equity", "interest_coverage",
        "ocf_margin", "fcf_margin", "ocf_to_net_income",
        "eps_growth",
    ]
    print(f"\n{'Ratio':<30} " + "  ".join(f"{p:>8}" for p in fy_periods))
    print("-" * (30 + 10 * len(fy_periods)))
    shown: set[str] = set()
    for key in _RATIO_ORDER:
        if key in ratio_display:
            row = ratio_display[key]
            vals = "  ".join(f"{row.get(p, '—'):>8}" for p in fy_periods)
            print(f"  {key:<28} {vals}")
            shown.add(key)
    for key in sorted(ratio_display):
        if key not in shown:
            row = ratio_display[key]
            vals = "  ".join(f"{row.get(p, '—'):>8}" for p in fy_periods)
            print(f"  {key:<28} {vals}")

    # ── DCF valuation ─────────────────────────────────────────────────────────
    print(f"\n[run_valuation] {ticker} — running DCF (3 scenarios)")
    dcf_assumptions = DCFAssumptions(
        wacc=wacc,
        terminal_growth=terminal_growth,
        forecast_years=forecast_years,
    )
    dcf_results = run_three_scenarios(ticker=ticker, fact_table=full_table, base=dcf_assumptions)

    for scenario, result in dcf_results.items():
        if result.intrinsic_value_per_share_vnd:
            print(
                f"  DCF {scenario:<5}: intrinsic={result.intrinsic_value_per_share_vnd:,.0f} VND/share"
                f"  EV={result.enterprise_value_vnd_bn:,.1f} VND bn"
                f"  (WACC={result.assumptions.wacc:.1%}, g={result.assumptions.terminal_growth:.1%})"
            )
        else:
            print(f"  DCF {scenario:<5}: could not compute — {result.warnings}")

    # ── Simplified DCF sensitivity (backward-compat, OCF-CAPEX FCF) ──────────
    print(f"\n[run_valuation] {ticker} — building simplified sensitivity table (OCF-CAPEX FCF)")
    sensitivity = build_sensitivity_table(
        ticker=ticker,
        fact_table=full_table,
        base_assumptions=dcf_assumptions,
    )
    _print_wacc_g_matrix(sensitivity["matrix"], sensitivity["g_range"], "Simplified FCF (OCF-CAPEX)")

    # ── Current market price ──────────────────────────────────────────────────
    print(f"\n[run_valuation] {ticker} — fetching current market price")
    current_price = _get_current_price(ticker)
    if current_price:
        print(f"[run_valuation] {ticker} current price: {current_price:,.0f} VND")
    else:
        print(f"[run_valuation] {ticker} current price: unavailable")

    # ── Multiples valuation ───────────────────────────────────────────────────
    print(f"[run_valuation] {ticker} — computing multiples")
    multiples = compute_multiples(
        ticker=ticker,
        fact_table=full_table,
        current_price_vnd=current_price,
        target_pe=target_pe,
        target_pb=target_pb,
        target_ev_ebitda=target_ev_ebitda,
    )

    m = multiples.to_dict()
    print(f"\n  Latest FY: {m['latest_fy']}")
    print(f"  EPS (VND):        {m['eps_vnd']:,.0f}" if m["eps_vnd"] else "  EPS: N/A")
    print(f"  Shares (mn):      {m['shares_mn']:,.1f}" if m["shares_mn"] else "  Shares: N/A")
    if m["pe_ratio"]:
        print(f"  Observed P/E:     {m['pe_ratio']:.1f}x")
    if m["implied_price_pe"]:
        print(f"  Implied (P/E={m['target_pe']}x):  {m['implied_price_pe']:,.0f} VND/share")
    if m["implied_price_ev_ebitda"]:
        print(f"  Implied (EV/EBITDA={m['target_ev_ebitda']}x): {m['implied_price_ev_ebitda']:,.0f} VND/share")
    if multiples.warnings:
        for w in multiples.warnings:
            print(f"  WARN: {w}")

    # ── Forecast (required for FCFF/FCFE) ────────────────────────────────────
    print(f"\n[run_valuation] {ticker} — running 5-year financial forecast")
    forecast = run_forecast(
        ticker=ticker,
        fact_table=full_table,
        assumptions=ForecastAssumptions(
            assumption_status=assumption_status,
            debt_schedule_approved=auto_approve_assumptions,
        ),
    )
    for w in forecast.warnings:
        print(f"  WARN (forecast): {w}")

    # Resolve reportable shares from explicit canonical facts. EPS-implied
    # shares are a reconciliation diagnostic and must not drive target price.
    from backend.analytics.shares import reportable_shares_mn
    _latest_fy = fy_periods[-1] if fy_periods else None
    _shares_mn = reportable_shares_mn(full_table, _latest_fy)
    if _shares_mn is None:
        print(
            f"[run_valuation] {ticker} — shares_outstanding fact missing; "
            "FCFF/FCFE target price and market-cap bridge will be blocked."
        )

    # Net borrowing schedule — sourced from forecast.debt_schedule (driver-based NB per year)
    _net_borrowing_sched = (
        forecast.debt_schedule.net_borrowing_schedule()
        if forecast.debt_schedule is not None and forecast.debt_schedule.is_fcfe_publishable
        else None
    )
    if _net_borrowing_sched:
        print(f"[run_valuation] {ticker} — net_borrowing_schedule connected: {_net_borrowing_sched}")
    else:
        print(f"[run_valuation] {ticker} — net_borrowing_schedule unavailable; FCFE will assume NB=0")

    # ── FCFF valuation (proper: EBIT(1-T)+D&A-CAPEX-DeltaNWC) ───────────────────
    print(f"\n[run_valuation] {ticker} — FCFF valuation (EBIT(1-T)+D&A-CAPEX-DeltaNWC, discounted at WACC)")
    # Wire forecast.tax_policy → WACCAssumptions so FCFF EBIT(1-T) uses the same
    # effective tax rate as the forecast P&L (avoids silent rate mismatch).
    wacc_assumptions = WACCAssumptions(
        assumption_status=assumption_status,
        tax_policy=forecast.tax_policy,
    )
    fcff_result = compute_fcff(
        ticker=ticker,
        forecast=forecast,
        fact_table=full_table,
        current_price_vnd=current_price,
        terminal_growth=terminal_growth,
        wacc_assumptions=wacc_assumptions,
        shares_mn=_shares_mn,
    )
    fd = fcff_result.to_dict()
    tv_check = compute_tv_weight(fd.get("pv_terminal_value"), fd.get("enterprise_value"))
    _print_fcf_summary("FCFF", fd, tv_check)
    for w in fcff_result.warnings:
        print(f"  WARN (FCFF): {w}")

    # ── FCFE valuation (Net Income+D&A-CAPEX-DeltaNWC+NetBorrowing, discounted at Re) ──
    print(f"\n[run_valuation] {ticker} — FCFE valuation (NI+D&A-CAPEX-DeltaNWC+NetBorr, discounted at Re)")
    coe_assumptions = CostOfEquityAssumptions(assumption_status=assumption_status)
    fcfe_result = compute_fcfe(
        ticker=ticker,
        forecast=forecast,
        fact_table=full_table,
        current_price_vnd=current_price,
        terminal_growth=terminal_growth,
        cost_of_equity_assumptions=coe_assumptions,
        shares_mn=_shares_mn,
        net_borrowing_schedule=_net_borrowing_sched,
    )
    fe = fcfe_result.to_dict()
    tv_check_fcfe = compute_tv_weight(fe.get("pv_terminal_value"), fe.get("equity_value"))
    _print_fcf_summary("FCFE", fe, tv_check_fcfe)
    for w in fcfe_result.warnings:
        print(f"  WARN (FCFE): {w}")

    # ── P/E Forward price (supplementary cross-check, NOT in blend) ─────────────────────────────────
    _eps_fy1_early = forecast.forecast_years[0].eps if forecast.forecast_years else None
    price_pe_forward: float | None = (
        _eps_fy1_early * target_pe if (_eps_fy1_early and _eps_fy1_early > 0) else None
    )
    _DEFAULT_PE = 15.0
    _pe_is_default = (target_pe == _DEFAULT_PE)
    _peer_data_source = "analyst_default_pending_peers" if _pe_is_default else "analyst_override"
    _pe_default_warning = (
        "target_pe=15.0x is model default — validate with peer-median P/E before publishing"
        if _pe_is_default else None
    )
    if price_pe_forward:
        print(f"\n[run_valuation] {ticker} — P/E Forward anchor: EPS_FY1={_eps_fy1_early:,.0f} × P/E={target_pe:.1f}x = {price_pe_forward:,.0f} VND/share")
        if _pe_is_default:
            print(f"  WARN [PEForward] target_pe = {target_pe:.1f}x is the model default — no peer dataset used. Validate with peer-median P/E before publishing.")
    else:
        print(f"\n[run_valuation] {ticker} — P/E Forward anchor unavailable (EPS_FY1 missing)")

    # ── 60/40 Blend: FCFF + FCFE ──────────────────────────────────────────────
    print(f"\n[run_valuation] {ticker} — Blended target price (60% FCFF + 40% FCFE)")
    blend = blend_dcf(
        ticker=ticker,
        price_fcff=fcff_result.target_price_vnd,
        price_fcfe=fcfe_result.target_price_vnd,
        current_price_vnd=current_price,
        pv_terminal_value_fcff=fcff_result.pv_terminal_value,
        enterprise_value_fcff=fcff_result.enterprise_value,
    )
    bd = blend.to_dict()
    print(f"  Price_FCFF:           {bd['price_fcff_vnd']:,.0f} VND/share" if bd['price_fcff_vnd'] else "  Price_FCFF: N/A")
    print(f"  Price_FCFE:           {bd['price_fcfe_vnd']:,.0f} VND/share" if bd.get('price_fcfe_vnd') else "  Price_FCFE: N/A")
    print(f"  Target Price (blend): {bd['target_price_dcf_vnd']:,.0f} VND/share" if bd['target_price_dcf_vnd'] else "  Target: N/A")
    if bd['upside_pct'] is not None:
        print(f"  Upside:               {bd['upside_pct']:.2%}")
    if bd['margin_of_safety'] is not None:
        print(f"  Margin of Safety:     {bd['margin_of_safety']:.2%}")
    if bd.get('fcff_fcfe_gap_pct') is not None:
        print(f"  FCFF/FCFE Gap:        {bd['fcff_fcfe_gap_pct']:.2%}")
    for w in blend.warnings:
        print(f"  WARN (blend): {w}")


    # ── Core P/E + Net Cash (Guidance Section 11) ────────────────────────────
    # Primary methodology for cash-rich companies: Core EPS × Target P/E + Net Cash/share
    _DEFAULT_CORE_PE = 19.0  # Vietnamese pharma peer median (18-22× range)
    print(f"\n[run_valuation] {ticker} — Core P/E + Net Cash (Guidance §11, core_pe={_DEFAULT_CORE_PE}×)")
    core_pe_result = compute_core_pe_net_cash(
        ticker=ticker,
        fact_table=full_table,
        forecast=forecast,
        target_core_pe=_DEFAULT_CORE_PE,
        shares_mn=_shares_mn,
    )
    cpnc = core_pe_result.to_dict()
    print(f"  Net Cash/share:       {cpnc['net_cash_per_share_vnd']:,.0f} VND  "
          f"(cash={cpnc['cash_vnd_bn']}, STI={cpnc['short_term_investments_vnd_bn']}, debt={cpnc['total_debt_vnd_bn']} bn)"
          if cpnc['net_cash_per_share_vnd'] is not None else "  Net Cash/share: N/A")
    print(f"  Net Fin. Income:      {cpnc['net_financial_income_vnd_bn']:.3f} bn  "
          f"(VAS EBIT {cpnc['vas_ebit_vnd_bn']:.1f} − pure EBIT {cpnc['pure_ebit_vnd_bn']:.1f})"
          if cpnc['net_financial_income_vnd_bn'] is not None else "  Net Fin. Income: N/A")
    print(f"  After-tax FI/share:   {cpnc['ati_per_share_vnd']:,.0f} VND"
          if cpnc['ati_per_share_vnd'] is not None else "  ATI/share: N/A")
    print(f"  EPS Forward:          {cpnc['eps_forward_vnd']:,.0f} VND"
          if cpnc['eps_forward_vnd'] is not None else "  EPS Forward: N/A")
    print(f"  Core EPS:             {cpnc['core_eps_vnd']:,.0f} VND  (= EPS − ATI/share)"
          if cpnc['core_eps_vnd'] is not None else "  Core EPS: N/A")
    print(f"  Target ({_DEFAULT_CORE_PE:.0f}× core + cash): {cpnc['target_price_vnd']:,.0f} VND/share"
          if cpnc['target_price_vnd'] is not None else "  Core P/E + Net Cash: N/A")
    for w in core_pe_result.warnings:
        print(f"  WARN (core_pe): {w}")

    # ── Cross-model validation: simplified DCF vs FCFF/FCFE blend ────────────
    _dcf_base_price = dcf_results["base"].intrinsic_value_per_share_vnd
    _blend_price = blend.target_price_dcf
    _capex_warnings = [w for r in dcf_results.values() for w in r.warnings if "CAPEX" in w or "Negative FCF" in w or "negative FCF" in w]

    print(f"\n[run_valuation] {ticker} — Cross-model validation")
    if _dcf_base_price and _blend_price and _blend_price > 0:
        _divergence = abs(_dcf_base_price / _blend_price - 1)
        _status = (
            "CRITICAL" if _divergence > 0.50
            else "WARN" if _divergence > 0.30
            else "OK"
        )
        print(f"  Simplified DCF (base): {_dcf_base_price:,.0f} VND/share")
        print(f"  FCFF/FCFE Blend:       {_blend_price:,.0f} VND/share")
        print(f"  Divergence:            {_divergence:.1%}  [{_status}]")
        if _status != "OK":
            print(
                f"  [{_status}] Simplified DCF deviates {_divergence:.1%} from FCFF/FCFE Blend. "
                "Likely cause: volatile OCF history or CAPEX sign issue. "
                "Use Blend 60/40 as primary valuation — NOT the simplified DCF."
            )
    if _capex_warnings:
        for w in _capex_warnings:
            print(f"  [CAPEX-AUDIT] {w}")
    if current_price and _dcf_base_price and _dcf_base_price > current_price * 2:
        print(
            f"  [SANITY] Simplified DCF ({_dcf_base_price:,.0f}) > 2x current price ({current_price:,.0f}). "
            "Do NOT present this as a target price. Driver-based FCFF/FCFE Blend is the valid estimate."
        )

    # ── FCFF sensitivity: WACC x g ────────────────────────────────────────────
    print(f"\n[run_valuation] {ticker} — FCFF sensitivity (WACC x terminal growth)")
    sens_fcff = build_fcff_sensitivity_table(
        ticker=ticker,
        forecast=forecast,
        fact_table=full_table,
        base_wacc_assumptions=_dc_replace(wacc_assumptions, wacc_override=fcff_result.wacc),
        shares_mn=_shares_mn,
        current_price_vnd=current_price,
        base_terminal_growth=terminal_growth,
    )
    _print_wacc_g_matrix(sens_fcff["matrix"], sens_fcff["g_range"], "Price_FCFF (VND/share)")

    # ── FCFE sensitivity: Re x g ──────────────────────────────────────────────
    print(f"\n[run_valuation] {ticker} — FCFE sensitivity (Re x terminal growth)")
    sens_fcfe = build_fcfe_sensitivity_table(
        ticker=ticker,
        forecast=forecast,
        fact_table=full_table,
        base_coe_assumptions=coe_assumptions,
        shares_mn=_shares_mn,
        current_price_vnd=current_price,
        net_borrowing_schedule=_net_borrowing_sched,
        base_terminal_growth=terminal_growth,
    )
    _print_wacc_g_matrix(sens_fcfe["matrix"], sens_fcfe["g_range"], "Price_FCFE (VND/share)", row_label="Re")

    # ── Blend sensitivity grid (FCFF rows × FCFE cols) ───────────────────────
    blend_grid: dict = {}
    if fcff_result.target_price_vnd and fcfe_result.target_price_vnd:
        base_fcff = fcff_result.target_price_vnd
        base_fcfe = fcfe_result.target_price_vnd
        step_fcff = max(5000, round(base_fcff * 0.05 / 5000) * 5000)
        step_fcfe = max(2000, round(base_fcfe * 0.05 / 2000) * 2000)
        p_fcff_range = [round(base_fcff + i * step_fcff) for i in range(-2, 3)]
        p_fcfe_range = [round(base_fcfe + i * step_fcfe) for i in range(-2, 3)]
        blend_grid = build_blend_sensitivity_table(
            price_fcff_range=p_fcff_range,
            price_fcfe_range=p_fcfe_range,
            current_price_vnd=current_price,
        )
        blend_grid["label"] = "FCFF rows × FCFE cols → Target_DCF"
        print(f"\n[run_valuation] {ticker} — Blend sensitivity (Price_FCFF × Price_FCFE -> Target_DCF)")
        _print_blend_grid(blend_grid)
    else:
        print(f"\n[run_valuation] {ticker} — Blend sensitivity skipped (FCFF or FCFE unavailable)")

    # ── P/E sensitivity ───────────────────────────────────────────────────────
    eps_fy1 = _eps_fy1_early   # already computed above
    pe_sens: dict = {}
    if eps_fy1 and eps_fy1 > 0:
        eps_range = [round(eps_fy1 * f) for f in [0.85, 0.92, 1.00, 1.08, 1.15]]
        pe_range = [10, 12, 14, 16, 18]
        pe_sens = build_pe_sensitivity_table(
            eps_fy1_range=eps_range,
            target_pe_range=pe_range,
            current_price_vnd=current_price,
            pe_label="Forward P/E",
        )
        print(f"\n[run_valuation] {ticker} — P/E sensitivity (EPS_FY1 x Forward P/E)")
        _print_pe_grid(pe_sens, current_price)
    else:
        print(f"\n[run_valuation] {ticker} — P/E sensitivity skipped (EPS_FY1 unavailable)")

    # ── EV/EBITDA sensitivity ─────────────────────────────────────────────────
    ebitda_fy1 = None
    if forecast.forecast_years:
        ebitda_fy1 = forecast.forecast_years[0].ebitda
    ev_sens: dict = {}
    net_debt_bn = fd.get("net_debt") or 0.0
    if ebitda_fy1 and ebitda_fy1 > 0 and _shares_mn:
        ebitda_range = [round(ebitda_fy1 * f, 1) for f in [0.85, 0.92, 1.00, 1.08, 1.15]]
        mult_range = [7.0, 8.0, 9.0, 10.0, 11.0]
        ev_sens = build_ev_ebitda_sensitivity_table(
            ebitda_fy1_range=ebitda_range,
            target_multiple_range=mult_range,
            net_debt_vnd_bn=net_debt_bn,
            shares_mn=_shares_mn,
            current_price_vnd=current_price,
        )
        print(f"\n[run_valuation] {ticker} — EV/EBITDA sensitivity (EBITDA rows x Multiple cols)")
        _print_ev_grid(ev_sens, current_price)
    else:
        print(f"\n[run_valuation] {ticker} — EV/EBITDA sensitivity skipped (EBITDA or shares unavailable)")

    # ── Assumption gate ───────────────────────────────────────────────────────
    _debt_method = (
        forecast.debt_schedule.forecast_method if forecast.debt_schedule else "missing"
    )
    _div_method = (
        forecast.dividend_schedule.method if forecast.dividend_schedule else "missing"
    )
    _mult_status = multiples.to_dict().get("relative_valuation_status", "pending_peer_dataset")
    _tax_approved = (
        forecast.tax_policy.approved if forecast.tax_policy else False
    )
    gate = build_gate_from_artifacts(
        data_quality_passed=True,          # snapshot guarantees accepted facts
        wacc_assumption_status=wacc_assumptions.assumption_status,
        cost_of_equity_status=coe_assumptions.assumption_status,
        forecast_assumption_status=forecast.assumptions.assumption_status,
        debt_schedule_method=_debt_method,
        tax_policy_approved=_tax_approved,
        dividend_schedule_approved=(_div_method != "missing"),
        peer_multiples_approved=(_mult_status not in ("pending_peer_dataset", "no_peer_data")),
        terminal_growth_approved=auto_approve_assumptions,
        final_recommendation_approved=False,
    )
    print(f"\n[run_valuation] {ticker} — Assumption gate: {gate.status}")
    if gate.blocking_reasons:
        for r in gate.blocking_reasons:
            print(f"  GATE: {r}")

    # ── Valuation confidence ──────────────────────────────────────────────────
    _fcfe_nb_method = _debt_method if _net_borrowing_sched else "missing"
    confidence = build_valuation_confidence(
        historical_facts_validated=True,
        forecast_assumption_status=forecast.assumptions.assumption_status,
        tax_policy_source=(forecast.tax_policy.source if forecast.tax_policy else "statutory_default"),
        tax_policy_approved=_tax_approved,
        debt_schedule_method=_debt_method,
        debt_schedule_approved=(_debt_method in ("zero_debt_policy", "manual_override")),
        dividend_method=_div_method,
        fcff_has_warnings=bool(fcff_result.warnings),
        fcfe_net_borrowing_method=_fcfe_nb_method,
        relative_pe_status=_mult_status,
        relative_ev_ebitda_status=_mult_status,
        gate_status=gate.status,
    )
    print(f"[run_valuation] {ticker} — Valuation confidence: final_rating={confidence.final_rating}")
    for r in confidence.reasons:
        print(f"  CONFIDENCE: {r}")

    # ── Build artifact ────────────────────────────────────────────────────────
    assumptions_record = {
        "wacc": wacc,
        "terminal_growth": terminal_growth,
        "forecast_years": forecast_years,
        "target_pe": target_pe,
        "target_pb": target_pb,
        "target_ev_ebitda": target_ev_ebitda,
        "auto_approve_assumptions": auto_approve_assumptions,
        "note": "Assumptions are defaults — must be reviewed and approved before use in final reports.",
    }
    formula_version = "valuation_v1_code_first_fcff_fcfe_blend"
    forecast_terminal_period = forecast.forecast_years[-1].label if forecast.forecast_years else None
    formula_traces = [
        _formula_trace(
            trace_id=f"{ticker}:WACC:{_latest_fy or 'NA'}",
            formula_id="wacc",
            formula_version=formula_version,
            output_name="wacc",
            output_value=fd.get("wacc"),
            unit="ratio",
            period=_latest_fy,
            input_fact_ids=_fact_ids(raw_facts, ["total_debt.ending", "equity.parent"], [_latest_fy] if _latest_fy else None),
            input_values=fd.get("wacc_breakdown", {}),
            calculation_steps=[
                {"step": "cost_of_equity", "value": fd.get("wacc_breakdown", {}).get("cost_of_equity")},
                {"step": "after_tax_cost_of_debt", "value": None if fd.get("wacc_breakdown", {}).get("cost_of_debt") is None else fd.get("wacc_breakdown", {}).get("cost_of_debt") * (1 - (fd.get("wacc_breakdown", {}).get("tax_rate") or 0))},
                {"step": "weighted_average_cost_of_capital", "value": fd.get("wacc")},
            ],
            warnings=fcff_result.warnings,
        ),
        _formula_trace(
            trace_id=f"{ticker}:FCFF:{forecast_terminal_period or 'NA'}",
            formula_id="fcff",
            formula_version=formula_version,
            output_name="fcff_equity_value",
            output_value=fd.get("equity_value"),
            unit="vnd_bn",
            period=forecast_terminal_period,
            input_fact_ids=_fact_ids(raw_facts, ["total_debt.ending", "cash_and_equivalents.ending", "shares_outstanding.weighted_avg"], [_latest_fy] if _latest_fy else None),
            input_values={
                "sum_pv_fcff": fd.get("sum_pv_fcff"),
                "pv_terminal_value": fd.get("pv_terminal_value"),
                "net_debt": fd.get("net_debt"),
                "shares_mn": fd.get("shares_mn"),
            },
            calculation_steps=[
                {"step": "enterprise_value=sum_pv_fcff+pv_terminal_value", "value": fd.get("enterprise_value")},
                {"step": "equity_value=enterprise_value-net_debt", "value": fd.get("equity_value")},
                {"step": "target_price=equity_value/shares", "value": fd.get("target_price_vnd")},
            ],
            warnings=fcff_result.warnings,
        ),
        _formula_trace(
            trace_id=f"{ticker}:FCFE:{forecast_terminal_period or 'NA'}",
            formula_id="fcfe",
            formula_version=formula_version,
            output_name="fcfe_equity_value",
            output_value=fe.get("equity_value"),
            unit="vnd_bn",
            period=forecast_terminal_period,
            input_fact_ids=_fact_ids(raw_facts, ["net_income.parent", "depreciation.total", "capex.total", "shares_outstanding.weighted_avg"], [_latest_fy] if _latest_fy else None),
            input_values={
                "sum_pv_fcfe": fe.get("sum_pv_fcfe"),
                "pv_terminal_value": fe.get("pv_terminal_value"),
                "shares_mn": fe.get("shares_mn"),
            },
            calculation_steps=[
                {"step": "equity_value=sum_pv_fcfe+pv_terminal_value", "value": fe.get("equity_value")},
                {"step": "target_price=equity_value/shares", "value": fe.get("target_price_vnd")},
            ],
            warnings=fcfe_result.warnings,
        ),
        _formula_trace(
            trace_id=f"{ticker}:TERMINAL_VALUE:FCFF",
            formula_id="terminal_value",
            formula_version=formula_version,
            output_name="fcff_terminal_value",
            output_value=fd.get("terminal_value"),
            unit="vnd_bn",
            period=forecast_terminal_period,
            input_values={
                "terminal_growth": fd.get("terminal_growth"),
                "wacc": fd.get("wacc"),
                "last_fcff": (fd.get("fcff_table") or [{}])[-1].get("fcff") if fd.get("fcff_table") else None,
            },
            calculation_steps=[
                {"step": "terminal_fcff=last_fcff*(1+g)", "value": None},
                {"step": "terminal_value=terminal_fcff/(wacc-g)", "value": fd.get("terminal_value")},
            ],
            warnings=fcff_result.warnings,
        ),
        _formula_trace(
            trace_id=f"{ticker}:BLEND_DCF",
            formula_id="blend_dcf",
            formula_version=formula_version,
            output_name="target_price_dcf_vnd",
            output_value=bd.get("target_price_dcf_vnd"),
            unit="vnd_per_share",
            period=forecast_terminal_period,
            input_values={
                "price_fcff_vnd": bd.get("price_fcff_vnd"),
                "price_fcfe_vnd": bd.get("price_fcfe_vnd"),
                "fcff_weight": bd.get("fcff_weight"),
                "fcfe_weight": bd.get("fcfe_weight"),
            },
            calculation_steps=[
                {"step": "target=fcff_weight*price_fcff+fcfe_weight*price_fcfe", "value": bd.get("target_price_dcf_vnd")},
            ],
            warnings=blend.warnings,
        ),
        _formula_trace(
            trace_id=f"{ticker}:SENSITIVITY:FCFF_WACC_G",
            formula_id="sensitivity_matrix",
            formula_version=formula_version,
            output_name="fcff_wacc_g",
            output_value={"rows": len(sens_fcff.get("matrix", {})), "columns": len(sens_fcff.get("g_range", []))},
            unit="matrix",
            period=None,
            input_values={"wacc_range": sens_fcff.get("wacc_range"), "g_range": sens_fcff.get("g_range")},
            calculation_steps=[
                {"step": "recompute target price across WACC and terminal growth grid", "value": "matrix"},
            ],
        ),
    ]

    artifact = {
        "ticker": ticker,
        "generated_at": generated_at.isoformat(),
        "formula_version": formula_version,
        "assumption_version": "default_assumptions_v1",
        "unit_policy": "VND per share; financial statement values follow canonical fact units",
        "currency": "VND",
        "period_scope": {"from_year": from_year, "to_year": to_year, "period_type": "FY"},
        "valuation_methods": ["core_pe_net_cash", "fcff", "fcfe", "blend_dcf_fcff_fcfe", "multiples", "sensitivity", "pe_forward_supplementary"],
        "snapshot_id": snapshot_id,
        "snapshot_as_of": snap["as_of_date"],
        "fy_periods": fy_periods,
        "assumptions": assumptions_record,
        "ratios": {k: {p: v for p, v in pv.items()} for k, pv in ratios.items()},
        "dcf_simplified": {sc: r.to_dict() for sc, r in dcf_results.items()},
        "core_pe_net_cash": core_pe_result.to_dict(),
        "fcff": fcff_result.to_dict(),
        "fcfe": fcfe_result.to_dict(),
        "blend_dcf": blend.to_dict(),
        "pe_forward": {
            "target_pe": target_pe,
            "eps_fy1_vnd": _eps_fy1_early,
            "price_pe_forward_vnd": price_pe_forward,
            "peer_data_source": _peer_data_source,
            "warnings": ([_pe_default_warning] if _pe_default_warning else []),
        },
        "forecast": forecast.to_dict(),
        "sensitivity": {
            "simplified_dcf": sensitivity,
            "fcff_wacc_g": sens_fcff,
            "fcfe_re_g": sens_fcfe,
            "blend_grid": blend_grid if blend_grid else {},
            "pe": pe_sens,
            "ev_ebitda": ev_sens,
        },
        "multiples": multiples.to_dict(),
        "current_price_vnd": current_price,
        "assumption_gate": gate.to_dict(),
        "valuation_confidence": confidence.to_dict(),
        "formula_traces": formula_traces,
    }
    from backend.evaluation.fpts_grade import build_valuation_bridge
    artifact["valuation_bridge"] = build_valuation_bridge(artifact)

    VALUATION_DIR.mkdir(parents=True, exist_ok=True)
    ts = generated_at.strftime("%Y%m%dT%H%M%S")
    out_path = VALUATION_DIR / "valuation.json"
    out_path.write_text(json.dumps(artifact, indent=2, default=str), encoding="utf-8")
    print(f"\n[run_valuation] Artifact saved: {out_path}")

    artifact["artifact_path"] = str(out_path)

    return artifact


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run code-first valuation for a VN pharma ticker.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--from-year", type=int, default=DEFAULT_FROM_YEAR, dest="from_year")
    parser.add_argument("--to-year", type=int, default=DEFAULT_TO_YEAR, dest="to_year")
    parser.add_argument("--wacc", type=float, default=0.10)
    parser.add_argument("--terminal-growth", type=float, default=0.03, dest="terminal_growth")
    parser.add_argument("--forecast-years", type=int, default=5, dest="forecast_years")
    parser.add_argument("--target-pe", type=float, default=15.0, dest="target_pe")
    parser.add_argument("--target-pb", type=float, default=2.5, dest="target_pb")
    parser.add_argument("--target-ev-ebitda", type=float, default=10.0, dest="target_ev_ebitda")
    parser.add_argument("--auto-approve-assumptions", action="store_true", dest="auto_approve_assumptions")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_valuation(
        ticker=args.ticker,
        from_year=args.from_year,
        to_year=args.to_year,
        wacc=args.wacc,
        terminal_growth=args.terminal_growth,
        forecast_years=args.forecast_years,
        target_pe=args.target_pe,
        target_pb=args.target_pb,
        target_ev_ebitda=args.target_ev_ebitda,
        auto_approve_assumptions=args.auto_approve_assumptions,
    )
    print("\n[run_valuation] done")


if __name__ == "__main__":
    main()
