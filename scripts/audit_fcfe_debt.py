"""Audit FCFE + debt completeness across every ticker that has a published run.

For each ticker's latest publishable run, reports:
  - debt forecast method + is_fcfe_publishable + (truncated) block reason
  - whether the forecast debt LEVEL renders (first forecast period not dashed)
  - which interest-bearing debt component types are present at the latest actual
  - FCFE price (blend.price_fcfe_vnd) — present or blocked, and why

Read-only. Usage:
    python scripts/audit_fcfe_debt.py
    python scripts/audit_fcfe_debt.py --tickers DHG,PVD,DBD
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.debug_debt_schedule import _load_dotenv, _latest_run_id  # noqa: E402

DEBT_COMPONENT_KEYS = [
    "total_debt.ending",
    "short_term_debt.ending",
    "long_term_debt.ending",
    "short_term_borrowings.ending",
    "long_term_borrowings.ending",
    "current_portion_ltd.ending",
    "lease_liabilities.ending",
]


def _all_tickers() -> list[str]:
    from backend.database.config import connect_with_retry, require_database_url

    with connect_with_retry(require_database_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT run_id FROM research.run_artifacts "
                "WHERE section_key = 'publishable_final_report_model' "
                "AND run_id LIKE 'run_%'"
            )
            rows = [r[0] for r in cur.fetchall()]
    tickers = sorted({rid.split("_")[1].upper() for rid in rows if "_" in rid})
    return tickers


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", default=None, help="comma-separated; default = all")
    args = parser.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    _load_dotenv()
    from backend.reporting import client_report_view_model as vm
    from backend.reporting.report_data_loader import _read_manifest_or_raise

    tickers = (
        [t.strip().upper() for t in args.tickers.split(",")]
        if args.tickers else _all_tickers()
    )

    hdr = f"{'Ticker':>6} | {'debt_method':>16} | {'fcfe_pub':>8} | {'fcst_debt':>9} | {'fcfe_price':>10} | debt_components / note"
    print(hdr)
    print("-" * len(hdr))

    incomplete: list[str] = []
    for tk in tickers:
        run_id = _latest_run_id(tk)
        if not run_id:
            print(f"{tk:>6} | {'NO RUN':>16} | {'—':>8} | {'—':>9} | {'—':>10} | no publishable run")
            incomplete.append(tk)
            continue
        try:
            mani = _read_manifest_or_raise(run_id, base_dir=ROOT)
            facts = vm._facts(tk, mani)
            fc = vm._forecast(tk, mani)
            rows = vm._forecast_by_label(fc)
            periods = vm._derive_periods(facts, fc)
            blend = vm._blend(tk, mani)

            ds = fc.get("debt_schedule") or {}
            method = ds.get("forecast_method") or "—"
            fcfe_pub = ds.get("is_fcfe_publishable")

            debt_vals = vm._interest_bearing_debt_values(facts, rows, periods)
            fcst_idx = [i for i, p in enumerate(periods) if str(p).endswith("F")]
            fcst_debt_shown = bool(fcst_idx) and debt_vals[fcst_idx[0]] is not None

            actuals = [p for p in periods if vm._is_actual(p)]
            comps = []
            if actuals:
                fp = vm._to_fact_period(actuals[-1])
                for k in DEBT_COMPONENT_KEYS:
                    if facts.get(k, {}).get(fp) is not None:
                        comps.append(k.split(".")[0])
            comp_str = ",".join(comps) if comps else "NONE"

            fcfe_price = blend.get("price_fcfe_vnd") if isinstance(blend, dict) else None
            fcfe_disp = f"{fcfe_price:.0f}" if isinstance(fcfe_price, (int, float)) else "BLOCKED"

            note = comp_str
            if fcfe_price is None:
                reason = ds.get("fcfe_block_reason") or ""
                note = f"{comp_str}  | fcfe blocked: {reason[:60]}"
                incomplete.append(tk)
            if not fcst_debt_shown and method not in ("zero_debt_policy", "missing"):
                incomplete.append(tk)

            print(
                f"{tk:>6} | {str(method):>16} | {str(fcfe_pub):>8} | "
                f"{('YES' if fcst_debt_shown else 'DASH'):>9} | {fcfe_disp:>10} | {note}"
            )
        except Exception as e:  # noqa: BLE001
            print(f"{tk:>6} | ERROR: {type(e).__name__}: {str(e)[:80]}")
            incomplete.append(tk)

    print("\n" + "=" * 80)
    if incomplete:
        print(f"Tickers needing attention (FCFE blocked or debt not shown): {sorted(set(incomplete))}")
    else:
        print("All tickers: FCFE present and forecast debt shown.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
