"""Generate charts C1–C7 for a ticker from valuation + facts artifacts.

Usage:
    python scripts/generate_charts.py --ticker DHG
    python scripts/generate_charts.py --ticker DHG --run-id RUN_20260601T120000

Reads:
    artifacts/valuation/{ticker}_*.json  — latest valuation artifact
    canonical_facts DB table             — historical per-period metrics

Writes PNGs to:
    artifacts/charts/
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backend.reporting.chart_generator import ChartGenerator, ChartSpec


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_latest_valuation(ticker: str) -> dict[str, Any]:
    """Return parsed JSON from the newest valuation artifact for ticker."""
    valuation_dir = _ROOT / "artifacts" / "valuation"
    pattern = f"{ticker}_*.json"
    candidates = sorted(valuation_dir.glob(pattern))
    # Filter out gate files (e.g. *_gate.json)
    candidates = [p for p in candidates if "gate" not in p.name]
    if not candidates:
        print(f"[WARN] No valuation artifacts found for {ticker} in {valuation_dir}")
        return {}
    latest = candidates[-1]
    print(f"[INFO] Loading valuation: {latest.name}")
    with open(latest, encoding="utf-8") as f:
        return json.load(f)


def _load_facts_from_db(ticker: str) -> dict[tuple[str, str], float]:
    """Query canonical_facts and return {(metric_name, period): value}.

    Falls back gracefully to empty dict if DB is unavailable.
    """
    dsn = os.getenv("DATABASE_URL", "postgresql://localhost/equity_research")
    try:
        import psycopg2  # type: ignore
        conn = psycopg2.connect(dsn)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT metric_name, period, value
            FROM canonical_facts
            WHERE ticker = %s
            ORDER BY period ASC, created_at DESC
            """,
            (ticker,),
        )
        rows = cur.fetchall()
        conn.close()
    except Exception as exc:
        print(f"[WARN] DB unavailable ({exc}); proceeding without fact data.")
        return {}

    # De-duplicate: keep first (i.e. latest created_at) per (metric, period)
    seen: dict[tuple[str, str], float] = {}
    for metric_name, period, value in rows:
        key = (metric_name, period)
        if key not in seen and value is not None:
            try:
                seen[key] = float(value)
            except (TypeError, ValueError):
                pass
    return seen


def _extract_ratio_series(
    ratios: dict[str, dict[str, float]],
    metric: str,
    periods: list[str],
) -> list[float]:
    """Pull per-period values from a valuation ratios dict."""
    series_map: dict[str, float] = ratios.get(metric, {})
    return [float(series_map.get(p, 0.0)) for p in periods]


def _build_spec(
    ticker: str,
    run_id: str,
    val: dict[str, Any],
    facts: dict[tuple[str, str], float],
) -> ChartSpec:
    """Assemble ChartSpec from valuation JSON + canonical facts."""

    periods: list[str] = val.get("fy_periods", [])
    ratios: dict = val.get("ratios", {})
    dcf_base: dict = val.get("dcf", {}).get("base", {})
    sensitivity: dict = val.get("sensitivity", {})
    multiples: dict = val.get("multiples", {})

    # --- Revenue (bn VND) ---
    # Prefer canonical facts; fall back to valuation FCF history
    revenue_bn: list[float] = []
    gross_profit_bn: list[float] = []
    net_income_bn: list[float] = []
    for p in periods:
        rev = facts.get(("revenue.net", p), 0.0)
        gp = facts.get(("gross_profit.total", p), 0.0)
        ni = facts.get(("net_income.parent", p), 0.0)
        revenue_bn.append(rev / 1e9 if rev > 1e6 else rev)         # normalise to bn
        gross_profit_bn.append(gp / 1e9 if gp > 1e6 else gp)
        net_income_bn.append(ni / 1e9 if ni > 1e6 else ni)

    # If no fact data, try to derive from ratios × FCF history (best effort)
    if not any(revenue_bn):
        fcf_hist: dict = dcf_base.get("fcf_history_vnd_bn", {})
        revenue_bn = [float(fcf_hist.get(p, 0.0)) for p in periods]

    # --- Margin series from ratios ---
    gross_margin_pct = [v * 100 for v in _extract_ratio_series(ratios, "gross_margin", periods)]
    net_margin_pct = [v * 100 for v in _extract_ratio_series(ratios, "net_margin", periods)]
    roe_pct = [v * 100 for v in _extract_ratio_series(ratios, "roe", periods)]

    # EBITDA / EBIT margins: look for ebitda_margin / ebit_margin in ratios
    ebitda_margin_pct = [v * 100 for v in _extract_ratio_series(ratios, "ebitda_margin", periods)]
    ebit_margin_pct = [v * 100 for v in _extract_ratio_series(ratios, "ebit_margin", periods)]

    # If ebitda not in ratios, approximate from net_margin
    if not any(ebitda_margin_pct):
        ebitda_margin_pct = [nm + 3.0 for nm in net_margin_pct]  # rough proxy
    if not any(ebit_margin_pct):
        ebit_margin_pct = [nm + 1.5 for nm in net_margin_pct]

    # --- EPS ---
    eps_vnd: list[float] = []
    for p in periods:
        eps = facts.get(("eps.basic", p), 0.0)
        eps_vnd.append(float(eps))
    # Fallback: use multiples EPS for latest period
    if not any(eps_vnd) and multiples.get("eps_vnd"):
        eps_vnd = [0.0] * max(len(periods) - 1, 0) + [float(multiples["eps_vnd"])]

    # --- P/E ---
    pe_x: list[float] = []
    current_price = float(val.get("current_price_vnd", 0.0))
    for i, p in enumerate(periods):
        eps = eps_vnd[i] if i < len(eps_vnd) else 0.0
        if eps and eps != 0:
            pe = current_price / eps
        else:
            pe = float(multiples.get("pe_ratio", 0.0))
        pe_x.append(round(pe, 1))

    # --- Forecast (from DCF projected FCF as proxy) ---
    projected_fcf: list[float] = dcf_base.get("projected_fcf_vnd_bn", [])
    n_forecast = min(5, len(projected_fcf))
    forecast_revenue_bn = projected_fcf[:n_forecast]
    # Approximate profit as net_margin × revenue (use latest net_margin)
    last_nm = net_margin_pct[-1] / 100 if net_margin_pct else 0.15
    forecast_profit_bn = [r * last_nm for r in forecast_revenue_bn]
    forecast_periods = [f"FY{2025 + i}E" for i in range(n_forecast)]

    # --- DCF Bridge ---
    pv_fcf = sum(dcf_base.get("pv_fcf_vnd_bn", []))
    pv_tv = float(dcf_base.get("pv_terminal_value_vnd_bn", 0.0))
    net_debt = float(dcf_base.get("net_debt_vnd_bn", 0.0))
    eq_val = float(dcf_base.get("equity_value_vnd_bn", 0.0))

    bridge_items: list[tuple[str, float]] = []
    if pv_fcf or pv_tv:
        bridge_items = [
            ("PV FCFF", pv_fcf),
            ("PV Terminal Value", pv_tv),
            ("Less: Net Debt", -net_debt if net_debt else 0.0),
            ("Equity Value", eq_val),
        ]

    # --- Sensitivity ---
    wacc_range_raw: list = sensitivity.get("wacc_range", [])
    g_range_raw: list = sensitivity.get("g_range", [])
    matrix_raw: dict = sensitivity.get("matrix", {})

    wacc_range = [float(w) * 100 for w in wacc_range_raw]  # convert to %
    g_range = [float(g) * 100 for g in g_range_raw]

    # matrix is stored as dict[wacc_str][g_str] → value
    matrix: list[list[float]] = []
    if isinstance(matrix_raw, dict) and wacc_range and g_range:
        wacc_keys = sorted(matrix_raw.keys(), key=float)
        for g_val in g_range_raw:
            row: list[float] = []
            for w_key in wacc_keys:
                sub = matrix_raw[w_key]
                if isinstance(sub, dict):
                    g_key = f"{float(g_val):.3f}"
                    val_cell = sub.get(g_key, 0.0)
                else:
                    val_cell = 0.0
                row.append(float(val_cell))
            matrix.append(row)
    elif isinstance(matrix_raw, list):
        matrix = [[float(v) for v in row] for row in matrix_raw]

    return ChartSpec(
        chart_id="",  # will be set per render call
        ticker=ticker,
        run_id=run_id,
        periods=periods,
        revenue_bn=revenue_bn,
        ebitda_margin_pct=ebitda_margin_pct,
        ebit_margin_pct=ebit_margin_pct,
        eps_vnd=eps_vnd,
        pe_x=pe_x,
        gross_margin_pct=gross_margin_pct,
        net_margin_pct=net_margin_pct,
        roe_pct=roe_pct,
        forecast_revenue_bn=forecast_revenue_bn,
        forecast_profit_bn=forecast_profit_bn,
        forecast_periods=forecast_periods,
        bridge_items=bridge_items,
        # C1 — not available from valuation artifacts alone
        price_series=[],
        benchmark_series=[],
        date_labels=[],
    ), wacc_range, g_range, matrix


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate charts C2–C7 for a ticker from valuation + facts artifacts."
    )
    parser.add_argument("--ticker", required=True, help="Ticker symbol, e.g. DHG")
    parser.add_argument("--run-id", default="", help="Optional run-id prefix for filenames")
    args = parser.parse_args()

    ticker = args.ticker.upper()
    run_id = args.run_id

    output_dir = _ROOT / "artifacts" / "charts"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load data
    val = _load_latest_valuation(ticker)
    facts = _load_facts_from_db(ticker)

    if not val:
        print("[WARN] No valuation data — charts will render with zeros/placeholders.")
        spec = ChartSpec(chart_id="", ticker=ticker, run_id=run_id)
        wacc_range: list[float] = []
        g_range: list[float] = []
        matrix: list[list[float]] = []
    else:
        spec, wacc_range, g_range, matrix = _build_spec(ticker, run_id, val, facts)

    gen = ChartGenerator(output_dir=output_dir)

    charts_rendered: list[Path] = []

    # C2 — Revenue & EBITDA/EBIT Trend (always)
    p = gen.render_c2_revenue_ebitda(spec)
    print(f"  [C2] {p}")
    charts_rendered.append(p)

    # C3 — EPS & P/E
    p = gen.render_c3_eps_pe(spec)
    print(f"  [C3] {p}")
    charts_rendered.append(p)

    # C4 — Margin & ROE
    p = gen.render_c4_margin_roe(spec)
    print(f"  [C4] {p}")
    charts_rendered.append(p)

    # C5 — Forecast
    p = gen.render_c5_forecast(spec)
    print(f"  [C5] {p}")
    charts_rendered.append(p)

    # C6 — DCF Bridge
    p = gen.render_c6_dcf_bridge(spec)
    print(f"  [C6] {p}")
    charts_rendered.append(p)

    # C7 — Sensitivity Heatmap
    p = gen.render_c7_sensitivity_heatmap(spec, wacc_range, g_range, matrix)
    print(f"  [C7] {p}")
    charts_rendered.append(p)

    # C1 — Price vs VNINDEX: only if price data exists (not from valuation JSON alone)
    if spec.price_series:
        p = gen.render_c1_price_vs_vnindex(spec)
        print(f"  [C1] {p}")
        charts_rendered.append(p)
    else:
        print("  [C1] Skipped — no price_series data (requires market price history)")

    print(f"\n[DONE] {len(charts_rendered)} chart(s) saved to {output_dir}")


if __name__ == "__main__":
    main()
