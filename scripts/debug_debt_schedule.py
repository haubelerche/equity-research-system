"""Debug the debt / net-debt calculation behind the "CÁC KHOẢN MỤC CĐKT VÀ DÒNG TIỀN" table.

Loads the real persisted artifacts (facts + forecast/debt_schedule) for a run and
prints, period-by-period, exactly how the reporting layer derives:

  - Nợ vay cuối năm        (interest-bearing / total debt, ending)
  - Tiền và tương đương     (cash-like assets)
  - Nợ ròng cuối năm        (net debt = debt - cash)
  - Thay đổi nợ ròng        (Δ net debt — what the report currently shows)
  - Δ Tổng nợ (gross)       (Δ interest-bearing debt — true financing borrowing proxy)
  - Net borrowing           (from the debt_schedule artifact, used by FCFE)

It reuses the SAME helper functions the renderer uses, so the numbers match the PDF.
Read-only: computes nothing into any artifact. Writes a log file under storage/.

Usage:
    python scripts/debug_debt_schedule.py --ticker DHG
    python scripts/debug_debt_schedule.py --ticker DHG --run-id run_dhg_20260612T073204_cfb79526af
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_dotenv() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    import os
    for line in env_file.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _latest_run_id(ticker: str) -> str | None:
    """Most-recent run_id for *ticker* that has a built final_report_model."""
    from backend.database.config import connect_with_retry, require_database_url

    with connect_with_retry(require_database_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT run_id FROM research.run_artifacts "
                "WHERE run_id LIKE %s AND section_key = 'final_report_model' "
                "ORDER BY run_id DESC LIMIT 1",
                (f"run_{ticker.lower()}%",),
            )
            row = cur.fetchone()
    return row[0] if row else None


def _fmt(v: object) -> str:
    if v is None:
        return "    —   "
    if isinstance(v, bool):
        return f"  {str(v):>5} "
    if isinstance(v, (int, float)):
        return f"{v:>8.1f}"
    return f"{str(v):>8}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", default="DHG")
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()
    ticker = args.ticker.upper()

    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Windows console is cp1252 by default
    except Exception:
        pass

    _load_dotenv()

    # Import the exact helpers the renderer uses so numbers match the PDF byte-for-byte.
    from backend.reporting import client_report_view_model as vm
    from backend.reporting.report_data_loader import _read_manifest_or_raise

    run_id = args.run_id or _latest_run_id(ticker)
    if not run_id:
        print(f"No run with a final_report_model found for {ticker}.")
        return 1

    manifest = _read_manifest_or_raise(run_id, base_dir=ROOT)
    facts = vm._facts(ticker, manifest)
    forecast = vm._forecast(ticker, manifest)
    forecast_rows = vm._forecast_by_label(forecast)
    periods = vm._derive_periods(facts, forecast)

    lines: list[str] = []

    def emit(s: str = "") -> None:
        print(s)
        lines.append(s)

    emit("=" * 100)
    emit(f"DEBT CALCULATION TRACE — {ticker}   run_id={run_id}")
    emit(f"Periods: {periods}")
    emit("All monetary values in tỷ đồng (VND bn). Source: same helpers as the rendered report.")
    emit("=" * 100)

    # ── Section 1: per-period reconstruction from facts / forecast_rows ──────────
    debt = vm._interest_bearing_debt_values(facts, forecast_rows, periods)
    cash = vm._cash_like_values(facts, forecast_rows, periods)
    net_debt = vm._net_debt_canonical(facts, forecast_rows, periods)

    delta_net_debt: list[object] = [None]
    for prev, curr in zip(net_debt, net_debt[1:]):
        delta_net_debt.append(None if prev is None or curr is None else curr - prev)

    delta_gross_debt: list[object] = [None]
    for prev, curr in zip(debt, debt[1:]):
        delta_gross_debt.append(None if prev is None or curr is None else curr - prev)

    emit("\n## 1. ROW-BY-ROW (what the report table shows)\n")
    header = (
        f"{'Period':>8} | {'Debt end':>8} | {'Cash':>8} | {'NetDebt':>8} | "
        f"{'ΔNetDebt':>8} | {'ΔGrossDebt':>10}"
    )
    emit(header)
    emit("-" * len(header))
    for i, p in enumerate(periods):
        kind = "F" if p.endswith("F") else "A"
        emit(
            f"{p:>8} | {_fmt(debt[i])} | {_fmt(cash[i])} | {_fmt(net_debt[i])} | "
            f"{_fmt(delta_net_debt[i])} | {_fmt(delta_gross_debt[i]):>10}   [{kind}]"
        )
    emit(
        '\nNOTE: The report row "Thay đổi nợ ròng" = ΔNetDebt column = Δ(debt − cash). '
        "It is dominated by CASH changes, not borrowing. The financing-true number is "
        "ΔGrossDebt (= net borrowing proxy)."
    )

    # ── Section 2: actual-period debt components (lineage from canonical facts) ──
    emit("\n## 2. ACTUAL-PERIOD DEBT COMPONENTS (canonical fact lineage)\n")
    comp_keys = [
        "total_debt.ending",
        "short_term_debt.ending",
        "current_portion_ltd.ending",
        "long_term_debt.ending",
        "lease_liabilities.ending",
        "short_term_borrowings.ending",
        "long_term_borrowings.ending",
        "cash_and_equivalents.ending",
        "short_term_investments.ending",
        "short_term_deposits.ending",
    ]
    for p in [pp for pp in periods if vm._is_actual(pp)]:
        fp = vm._to_fact_period(p)
        emit(f"  [{p}]  (fact period key = {fp})")
        for k in comp_keys:
            raw = facts.get(k, {}).get(fp)
            val = vm._fact_value(facts, k, fp)
            present = "present" if raw is not None else "MISSING"
            emit(f"      {k:<34} {present:>8}  ->  {_fmt(val)}")
        emit("")

    # ── Section 3: debt_schedule artifact (the FCFE source of truth) ────────────
    emit("\n## 3. debt_schedule ARTIFACT (drives forecast debt + FCFE net borrowing)\n")
    ds = forecast.get("debt_schedule") or {}
    if not ds:
        emit("  !! No debt_schedule artifact present in forecast payload.")
    else:
        emit(f"  forecast_method      = {ds.get('forecast_method')}")
        emit(f"  status               = {ds.get('status')}")
        emit(f"  is_fcfe_publishable  = {ds.get('is_fcfe_publishable')}")
        emit(f"  fcfe_block_reason    = {ds.get('fcfe_block_reason')}")
        for w in ds.get("warnings", []) or []:
            emit(f"  warning: {w}")

        for section in ("historical_rows", "forecast_rows"):
            rows = ds.get(section) or []
            if not rows:
                continue
            emit(f"\n  -- {section} --")
            cols = ["label", "beginning_interest_bearing_debt", "new_borrowing",
                    "debt_repayment", "ending_interest_bearing_debt", "net_borrowing",
                    "method", "confidence", "identity_check_passes"]
            emit("    " + " | ".join(f"{c.split('_')[0][:8]:>8}" if c != "label" else f"{'label':>7}" for c in cols))
            for r in rows:
                vals = []
                for c in cols:
                    v = r.get(c)
                    vals.append(f"{v:>7}" if c == "label" else _fmt(v))
                emit("    " + " | ".join(vals))
                if r.get("warning"):
                    emit(f"        warning: {r['warning']}")

    # ── Section 4: anomaly checks ───────────────────────────────────────────────
    emit("\n## 4. ANOMALY CHECKS\n")
    issues: list[str] = []

    # 4a. Discontinuity between last actual ending debt and first forecast beginning debt.
    actuals = [p for p in periods if vm._is_actual(p)]
    forecasts = [p for p in periods if p.endswith("F")]
    if actuals and forecasts and ds:
        last_actual_debt = debt[periods.index(actuals[-1])]
        f_rows = {r.get("label"): r for r in (ds.get("forecast_rows") or [])}
        first_f = f_rows.get(forecasts[0], {})
        begin_f = first_f.get("beginning_interest_bearing_debt")
        if last_actual_debt is not None and begin_f is not None and abs(last_actual_debt - begin_f) > 1.0:
            issues.append(
                f"DISCONTINUITY: last actual debt {actuals[-1]}={last_actual_debt:.1f} but forecast "
                f"{forecasts[0]} begins at {begin_f:.1f}. Forecast does not roll forward from the "
                "real closing balance."
            )

    # 4b. Suspicious zero / large drop in the actual debt series.
    for prev_p, curr_p, prev_v, curr_v in zip(periods, periods[1:], debt, debt[1:]):
        if prev_v and curr_v == 0:
            raw = facts.get("short_term_debt.ending", {}).get(vm._to_fact_period(curr_p))
            sourced = isinstance(raw, dict) and bool(raw.get("fact_id"))
            issues.append(
                f"DEBT→0: {curr_p} interest-bearing debt = 0 while {prev_p} = {prev_v:.1f}. "
                + ("Backed by a real sourced fact (fact_id + source_uri present) — treat as a "
                   "genuine pay-down; forecast must roll forward from 0."
                   if sourced else
                   "No fact_id on the source row — verify the BCTC actually shows zero debt "
                   "(possible parse miss coerced to 0).")
            )

    # 4c. ΔNetDebt vs ΔGrossDebt divergence (cash-driven, not borrowing).
    for p, dnd, dgd in zip(periods[1:], delta_net_debt[1:], delta_gross_debt[1:]):
        if isinstance(dnd, (int, float)) and isinstance(dgd, (int, float)) and abs(dnd - dgd) > 50:
            issues.append(
                f"LABEL RISK [{p}]: 'Thay đổi nợ ròng'={dnd:.0f} but actual change in gross debt"
                f"={dgd:.0f}. The reported number reflects cash build-up, NOT financing/borrowing."
            )

    # 4d. FCFE publishability.
    if ds and not ds.get("is_fcfe_publishable", False):
        issues.append(
            f"FCFE BLOCK: debt_schedule.method='{ds.get('forecast_method')}', "
            "net_borrowing is NOT high-confidence — FCFE leg should not be published from it."
        )

    if issues:
        for n, msg in enumerate(issues, 1):
            emit(f"  [{n}] {msg}")
    else:
        emit("  No anomalies detected.")

    # ── Write log ───────────────────────────────────────────────────────────────
    out_dir = ROOT / "storage" / "debug"
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / f"debt_trace_{ticker}_{run_id}.log"
    log_path.write_text("\n".join(lines), encoding="utf-8")
    emit(f"\nLog written to: {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
