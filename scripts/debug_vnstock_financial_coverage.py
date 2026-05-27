"""Empirical coverage matrix for vnstock financial data availability.

Usage:
    PYTHONUTF8=1 python scripts/debug_vnstock_financial_coverage.py --tickers DHG IMP DMC TRA DBD --years 5
    PYTHONUTF8=1 python scripts/debug_vnstock_financial_coverage.py --tickers DHG --years 5 --verbose

Outputs:
    artifacts/data_quality/vnstock_financial_coverage_matrix.csv
    artifacts/raw/vnstock/{ticker}/{provider}/{statement_type}_{period_type}.csv
    artifacts/data_quality/{ticker}_vnstock_raw_coverage.json
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_PROJECT_ROOT = str(_Path(__file__).resolve().parents[1])
if _PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, _PROJECT_ROOT)
if "" in _sys.path:
    _sys.path = [p for p in _sys.path if p != ""] + [""]

import argparse
import csv
import json
import os
import traceback
from datetime import UTC, datetime
from typing import Any

import pandas as pd

_env_file = _Path(__file__).resolve().parents[1] / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip(chr(34)).strip(chr(39)))

ROOT = _Path(__file__).resolve().parents[1]
ARTIFACTS_RAW = ROOT / "artifacts" / "raw" / "vnstock"
ARTIFACTS_DQ = ROOT / "artifacts" / "data_quality"

MVP_TICKERS = ["DHG", "IMP", "DMC", "TRA", "DBD"]
PROVIDERS = ["VCI", "KBS"]
STATEMENT_TYPES = ["income_statement", "balance_sheet", "cash_flow", "ratio"]
PERIOD_TYPES = ["year", "quarter"]

REQUIRED_TAXONOMY_KEYS = [
    "revenue.net",
    "gross_profit.total",
    "net_income.parent",
    "eps.basic",
    "cash_and_equivalents.ending",
    "inventory.ending",
    "total_debt.ending",
    "equity.parent",
    "operating_cash_flow.total",
    "capex.total",
]

STATEMENT_REQUIRED_KEYS = {
    "income_statement": ["revenue.net", "gross_profit.total", "net_income.parent", "eps.basic"],
    "balance_sheet": ["cash_and_equivalents.ending", "inventory.ending", "total_debt.ending", "equity.parent"],
    "cash_flow": ["operating_cash_flow.total", "capex.total"],
    "ratio": [],
}


def _fetch_statement(
    ticker: str,
    provider: str,
    statement: str,
    period: str,
    max_retries: int = 3,
) -> tuple[pd.DataFrame | None, str | None]:
    """Fetch a single statement with retry on rate limit. Returns (dataframe, error_message)."""
    import time

    last_err: str | None = None
    for attempt in range(max_retries):
        try:
            from vnstock.api.financial import Finance
            client = Finance(source=provider, symbol=ticker, period=period)
            if statement == "income_statement":
                df = client.income_statement(period=period, lang="vi")
            elif statement == "balance_sheet":
                df = client.balance_sheet(period=period, lang="vi")
            elif statement == "cash_flow":
                df = client.cash_flow(period=period, lang="vi")
            elif statement == "ratio":
                df = client.ratio(period=period, lang="vi")
            else:
                return None, f"Unknown statement type: {statement}"
            return df, None
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
            # Rate limit messages include keywords; wait proportionally
            err_lower = last_err.lower()
            if "rate limit" in err_lower or "giới hạn" in err_lower or "terminated" in err_lower:
                wait_s = 65 * (attempt + 1)
                print(f"    [rate-limit] waiting {wait_s}s before retry {attempt + 1}/{max_retries} ...", flush=True)
                time.sleep(wait_s)
            else:
                break  # Non-rate-limit error — don't retry
    return None, last_err


def _period_columns(df: pd.DataFrame) -> list[str]:
    import re
    return [c for c in df.columns if re.search(r"20\d{2}", str(c))]


def _parse_periods(period_cols: list[str]) -> list[tuple[int, str]]:
    import re
    result: list[tuple[int, str]] = []
    for col in period_cols:
        cleaned = str(col).strip().upper()
        year_match = re.search(r"(20\d{2})", cleaned)
        if not year_match:
            continue
        year = int(year_match.group(1))
        q_match = re.search(r"Q([1-4])", cleaned)
        if q_match:
            result.append((year, f"Q{q_match.group(1)}"))
        else:
            result.append((year, "FY"))
    return result


def _save_raw_snapshot(
    df: pd.DataFrame,
    ticker: str,
    provider: str,
    statement: str,
    period: str,
    fetch_time: str,
) -> Path:
    out_dir = ARTIFACTS_RAW / ticker / provider
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{statement}_{period}.csv"
    df.to_csv(out_path, index=True, encoding="utf-8-sig")

    meta_path = out_dir / f"{statement}_{period}_meta.json"
    period_cols = _period_columns(df)
    parsed = _parse_periods(period_cols)
    years = sorted({y for y, _ in parsed}) if parsed else []
    meta = {
        "ticker": ticker,
        "provider": provider,
        "statement": statement,
        "period_type": period,
        "fetch_time": fetch_time,
        "row_count": len(df),
        "column_names": list(df.columns),
        "period_columns": period_cols,
        "years_found": years,
        "min_period": min(period_cols, default=None),
        "max_period": max(period_cols, default=None),
        "total_periods": len(period_cols),
    }
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_path


def _count_nonzero_periods(df: pd.DataFrame, period_cols: list[str]) -> dict[str, int]:
    nonzero: dict[str, int] = {}
    for col in period_cols:
        col_data = df[col].dropna()
        try:
            numeric = pd.to_numeric(col_data, errors="coerce").dropna()
            nz = int((numeric != 0).sum())
        except Exception:  # noqa: BLE001
            nz = 0
        nonzero[str(col)] = nz
    return nonzero


def probe_ticker(
    ticker: str,
    years: int,
    verbose: bool = False,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    fetch_time = datetime.now(UTC).isoformat()

    for provider in PROVIDERS:
        for statement in STATEMENT_TYPES:
            for period in PERIOD_TYPES:
                row: dict[str, Any] = {
                    "ticker": ticker,
                    "provider": provider,
                    "statement": statement,
                    "period_type": period,
                    "fetch_time": fetch_time,
                    "status": None,
                    "error": None,
                    "row_count": 0,
                    "total_periods": 0,
                    "years_found": 0,
                    "min_period": None,
                    "max_period": None,
                    "periods_ge_5y": False,
                    "nonzero_cells": 0,
                }
                if verbose:
                    print(f"  [{ticker}] {provider} / {statement} / {period} ...", flush=True)

                df, err = _fetch_statement(ticker=ticker, provider=provider, statement=statement, period=period)
                if err or df is None or df.empty:
                    row["status"] = "error" if err else "empty"
                    row["error"] = err or "empty dataframe"
                    rows.append(row)
                    if verbose:
                        print(f"    → {row['status']}: {row['error'][:80]}", flush=True)
                    continue

                period_cols = _period_columns(df)
                parsed = _parse_periods(period_cols)
                years_found = sorted({y for y, _ in parsed})
                total_periods = len(period_cols)
                nonzero_map = _count_nonzero_periods(df, period_cols)
                total_nonzero = sum(nonzero_map.values())

                # Check if we have >= target years worth of data
                target_year = datetime.now(UTC).year - years
                years_meeting_target = [y for y in years_found if y >= target_year]

                row.update({
                    "status": "ok",
                    "row_count": len(df),
                    "total_periods": total_periods,
                    "years_found": len(years_found),
                    "min_period": min(period_cols, default=None),
                    "max_period": max(period_cols, default=None),
                    "periods_ge_5y": len(years_meeting_target) >= years,
                    "nonzero_cells": total_nonzero,
                    "years_list": ",".join(str(y) for y in years_found),
                })
                rows.append(row)

                # Save raw snapshot
                try:
                    out_path = _save_raw_snapshot(
                        df=df,
                        ticker=ticker,
                        provider=provider,
                        statement=statement,
                        period=period,
                        fetch_time=fetch_time,
                    )
                    row["raw_snapshot_path"] = str(out_path)
                except Exception as snap_err:  # noqa: BLE001
                    row["raw_snapshot_path"] = f"ERROR: {snap_err}"

                if verbose:
                    print(
                        f"    → ok | rows={len(df)} periods={total_periods} "
                        f"years={years_found} nonzero_cells={total_nonzero}",
                        flush=True,
                    )

    return rows


def _build_ticker_completeness(
    ticker: str,
    probe_rows: list[dict[str, Any]],
    years: int,
) -> dict[str, Any]:
    """Summarize per-ticker completeness across the best provider per statement."""
    from scripts.dataset.config_io import load_financial_taxonomy

    taxonomy = load_financial_taxonomy()

    best: dict[tuple[str, str], dict[str, Any]] = {}
    for row in probe_rows:
        if row["ticker"] != ticker or row["status"] != "ok":
            continue
        key = (row["statement"], row["period_type"])
        existing = best.get(key)
        if existing is None or row["years_found"] > existing["years_found"]:
            best[key] = row

    summary: dict[str, Any] = {
        "ticker": ticker,
        "years_requested": years,
        "generated_at": datetime.now(UTC).isoformat(),
        "statements": {},
        "overall_status": "unknown",
    }

    for statement in STATEMENT_TYPES:
        stmt_info: dict[str, Any] = {}
        for period in PERIOD_TYPES:
            b = best.get((statement, period))
            if b is None:
                stmt_info[period] = {"status": "no_data", "years_found": 0, "periods": 0}
            else:
                stmt_info[period] = {
                    "status": b["status"],
                    "provider_used": b["provider"],
                    "years_found": b["years_found"],
                    "years_list": b.get("years_list", ""),
                    "total_periods": b["total_periods"],
                    "nonzero_cells": b["nonzero_cells"],
                    "meets_5y_target": b.get("periods_ge_5y", False),
                }
        summary["statements"][statement] = stmt_info

    # Determine overall status
    required_ok = all(
        summary["statements"].get(stmt, {}).get("year", {}).get("status") == "ok"
        for stmt in ["income_statement", "balance_sheet", "cash_flow"]
    )
    sufficient_history = all(
        summary["statements"].get(stmt, {}).get("year", {}).get("years_found", 0) >= 3
        for stmt in ["income_statement", "balance_sheet", "cash_flow"]
    )
    if required_ok and sufficient_history:
        summary["overall_status"] = "pass"
    elif required_ok:
        summary["overall_status"] = "warn_history_short"
    else:
        summary["overall_status"] = "fail"

    return summary


def run_coverage(tickers: list[str], years: int, verbose: bool, inter_ticker_sleep: int = 65) -> None:
    import time

    ARTIFACTS_DQ.mkdir(parents=True, exist_ok=True)
    ARTIFACTS_RAW.mkdir(parents=True, exist_ok=True)

    all_rows: list[dict[str, Any]] = []

    for i, ticker in enumerate(tickers):
        if i > 0 and inter_ticker_sleep > 0:
            print(f"\n[coverage] Sleeping {inter_ticker_sleep}s before next ticker (rate limit mitigation) ...", flush=True)
            time.sleep(inter_ticker_sleep)
        print(f"\n[coverage] Probing {ticker} ...", flush=True)
        rows = probe_ticker(ticker=ticker, years=years, verbose=verbose)
        all_rows.extend(rows)

        # Per-ticker completeness
        completeness = _build_ticker_completeness(ticker=ticker, probe_rows=rows, years=years)
        completeness_path = ARTIFACTS_DQ / f"{ticker}_vnstock_raw_coverage.json"
        completeness_path.write_text(
            json.dumps(completeness, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"[coverage] {ticker} overall_status={completeness['overall_status']}")
        for stmt, periods in completeness["statements"].items():
            for ptype, info in periods.items():
                if isinstance(info, dict):
                    s = info.get("status", "?")
                    yf = info.get("years_found", 0)
                    tp = info.get("total_periods", 0)
                    nz = info.get("nonzero_cells", 0)
                    prov = info.get("provider_used", "-")
                    print(f"  {stmt:20s} / {ptype:8s}: status={s} years={yf} periods={tp} nonzero={nz} provider={prov}")

    # Write coverage matrix CSV
    matrix_path = ARTIFACTS_DQ / "vnstock_financial_coverage_matrix.csv"
    if all_rows:
        fieldnames = [
            "ticker", "provider", "statement", "period_type", "fetch_time",
            "status", "error", "row_count", "total_periods", "years_found",
            "min_period", "max_period", "periods_ge_5y", "nonzero_cells", "years_list",
            "raw_snapshot_path",
        ]
        with matrix_path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(all_rows)
        print(f"\n[coverage] Matrix saved → {matrix_path}")
    else:
        print("[coverage] No data rows to write.")

    # Print summary table
    print("\n=== COVERAGE SUMMARY ===")
    print(f"{'TICKER':<8} {'PROVIDER':<8} {'STATEMENT':<22} {'PERIOD':<8} {'STATUS':<8} {'YEARS':>5} {'PERIODS':>7} {'NONZERO':>8}")
    print("-" * 80)
    for row in sorted(all_rows, key=lambda r: (r["ticker"], r["provider"], r["statement"], r["period_type"])):
        print(
            f"{row['ticker']:<8} {row['provider']:<8} {row['statement']:<22} "
            f"{row['period_type']:<8} {row.get('status', '?'):<8} "
            f"{row.get('years_found', 0):>5} {row.get('total_periods', 0):>7} "
            f"{row.get('nonzero_cells', 0):>8}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Empirical vnstock financial data coverage matrix.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--tickers", nargs="+", default=MVP_TICKERS,
        help="Tickers to probe.",
    )
    parser.add_argument("--years", type=int, default=5, help="Target years of history.")
    parser.add_argument("--verbose", action="store_true", help="Print per-fetch progress.")
    parser.add_argument(
        "--inter-ticker-sleep", type=int, default=65,
        help="Seconds to sleep between tickers to respect vnstock guest rate limit (20 req/min). Set 0 to disable.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    tickers = [t.strip().upper() for t in args.tickers]
    print(f"[coverage] Probing tickers={tickers} providers={PROVIDERS} statements={STATEMENT_TYPES} periods={PERIOD_TYPES}")
    run_coverage(tickers=tickers, years=args.years, verbose=args.verbose, inter_ticker_sleep=args.inter_ticker_sleep)


if __name__ == "__main__":
    main()
