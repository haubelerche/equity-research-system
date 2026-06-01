"""Run full report rendering pipeline for one or all MVP tickers.

Steps per ticker:
  1. generate_charts.py  — PNG charts
  2. render_report.py    — HTML report (+ PDF if --pdf)
  3. artifact_writer     — 5 canonical artifacts

Usage:
    python scripts/run_full_pipeline.py --ticker DHG
    python scripts/run_full_pipeline.py --all
    python scripts/run_full_pipeline.py --all --pdf
"""
from __future__ import annotations

import argparse
import glob
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.reporting.artifact_writer import ArtifactWriter, RunArtifacts  # noqa: E402

# ---------------------------------------------------------------------------
# Deprecation Guard
# ---------------------------------------------------------------------------
import os as _os_dep

_FORCE_LEGACY = "--force-legacy" in sys.argv or _os_dep.getenv("ALLOW_LEGACY_PIPELINE") == "1"
if not _FORCE_LEGACY:
    print(
        "\n[DEPRECATED] run_full_pipeline.py is a render-only demo script.\n"
        "It does NOT run ingestion, facts, valuation, citation, or evaluation.\n"
        "Canonical artifacts written by this script are EMPTY placeholders.\n"
        "\nUse the production pipeline instead:\n"
        "  python scripts/run_research.py --ticker DHG\n"
        "\nFor local chart rendering only (bypasses all gates):\n"
        "  python scripts/run_full_pipeline.py --ticker DHG --force-legacy\n",
        file=sys.stderr,
    )
    sys.exit(1)
# Strip --force-legacy from argv before argparse sees it
sys.argv = [a for a in sys.argv if a != "--force-legacy"]

MVP_TICKERS = ["DHG", "IMP", "DMC", "TRA", "DBD"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(cmd: list[str], description: str) -> tuple[bool, str]:
    """Run a subprocess command, return (ok, output_snippet).

    Sets PYTHONPATH to ROOT so that all scripts can import `backend.*`
    regardless of how they set up sys.path internally.
    """
    import os as _os
    env = _os.environ.copy()
    existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(ROOT) + (_os.pathsep + existing_pp if existing_pp else "")

    try:
        result = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=300,
            env=env,
        )
        ok = result.returncode == 0
        snippet = (result.stdout + result.stderr).strip()[-500:] if not ok else ""
        return ok, snippet
    except subprocess.TimeoutExpired:
        return False, f"TIMEOUT: {description}"
    except Exception as exc:
        return False, f"ERROR: {exc}"


def _count_charts(ticker: str) -> int:
    """Count how many chart PNGs exist for this ticker."""
    charts_dir = ROOT / "artifacts" / "charts"
    if not charts_dir.exists():
        return 0
    return len(list(charts_dir.glob(f"{ticker}_C*.png")))


def _html_exists(ticker: str) -> bool:
    html_dir = ROOT / "artifacts" / "reports_html"
    if not html_dir.exists():
        return False
    return any(html_dir.glob(f"{ticker}_*.html")) or any(html_dir.glob(f"*{ticker}*.html"))


def _count_artifacts(ticker: str, run_id: str) -> int:
    """Count how many of the 5 canonical artifact files exist for this run."""
    dirs_and_suffixes = [
        ("claim_ledgers", "claim_ledger"),
        ("source_manifests", "source_manifest"),
        ("valuation_results", "valuation_result"),
        ("eval_results", "eval_result"),
        ("run_logs", "run_log"),
    ]
    count = 0
    for folder, suffix in dirs_and_suffixes:
        target = ROOT / "artifacts" / folder / f"{run_id}_{ticker}_{suffix}.json"
        if target.exists():
            count += 1
    return count


def _write_artifacts(ticker: str) -> tuple[str, int]:
    """Write 5 canonical artifacts for this ticker. Returns (run_id, artifact_count)."""
    # Load latest valuation JSON if available
    val_pattern = str(ROOT / "artifacts" / "valuation" / f"{ticker}_*_valuation.json")
    files = sorted(glob.glob(val_pattern))
    if files:
        with open(files[-1], encoding="utf-8") as _f:
            val: dict[str, Any] = json.load(_f)
    else:
        val = {}

    run_id = f"RUN_{ticker}_{datetime.now().strftime('%Y%m%dT%H%M%S')}"
    arts = RunArtifacts(
        run_id=run_id,
        ticker=ticker,
        report_date=datetime.now().strftime("%Y-%m-%d"),
        data_cutoff="2025-12-31",
        rating="UNDER_REVIEW",
        current_price=float(val.get("current_price", 0.0) or 0.0),
        target_price=float(val.get("target_price", 0.0) or 0.0),
        upside_pct=float(val.get("upside_pct", 0.0) or 0.0),
        wacc=float(val.get("wacc", 0.0) or 0.0),
        terminal_growth=float(val.get("terminal_growth", 0.0) or 0.0),
        equity_value=float(val.get("equity_value", 0.0) or 0.0),
        shares_outstanding=float(val.get("shares_outstanding", 0.0) or 0.0),
        implied_price=float(val.get("implied_price", 0.0) or 0.0),
        gate_results=[],
        claims=[],
        sources=[],
        fcff_rows=[],
        sensitivity={},
        scenarios={},
        assumptions=[],
        report_status="DRAFT",
    )
    ArtifactWriter(base_dir=ROOT / "artifacts").write_all(arts)
    count = _count_artifacts(ticker, run_id)
    return run_id, count


# ---------------------------------------------------------------------------
# Per-ticker pipeline
# ---------------------------------------------------------------------------

def run_ticker(ticker: str, pdf: bool = False) -> dict[str, Any]:
    """Run the full pipeline for a single ticker. Returns result dict."""
    result: dict[str, Any] = {
        "ticker": ticker,
        "charts_ok": False,
        "html_ok": False,
        "artifacts_ok": False,
        "chart_count": 0,
        "artifact_count": 0,
        "errors": [],
    }

    # Step 1 — generate charts
    charts_cmd = [sys.executable, "scripts/generate_charts.py", "--ticker", ticker]
    ok, err = _run(charts_cmd, f"generate_charts {ticker}")
    result["charts_ok"] = ok
    if not ok:
        result["errors"].append(f"charts: {err[:200]}")

    result["chart_count"] = _count_charts(ticker)

    # Step 2 — render HTML (and optionally PDF)
    render_cmd = [sys.executable, "scripts/render_report.py", "--ticker", ticker]
    if pdf:
        render_cmd.append("--pdf")
    ok, err = _run(render_cmd, f"render_report {ticker}")
    result["html_ok"] = ok or _html_exists(ticker)
    if not ok:
        result["errors"].append(f"render: {err[:200]}")

    # Step 3 — write 5 canonical artifacts
    try:
        run_id, count = _write_artifacts(ticker)
        result["artifacts_ok"] = count >= 5
        result["artifact_count"] = count
        result["run_id"] = run_id
    except Exception as exc:
        result["artifacts_ok"] = False
        result["artifact_count"] = 0
        result["errors"].append(f"artifacts: {exc}")

    return result


# ---------------------------------------------------------------------------
# Summary printer
# ---------------------------------------------------------------------------

def print_summary(results: list[dict[str, Any]]) -> None:
    print("\n=== PIPELINE SUMMARY ===")
    all_ok = True
    for r in results:
        ticker = r["ticker"]
        charts = r["chart_count"]
        html = "yes" if r["html_ok"] else "NO"
        arts = r["artifact_count"]
        status = "OK" if (r["charts_ok"] and r["html_ok"] and r["artifacts_ok"]) else "PARTIAL"
        if r["errors"] and not (r["charts_ok"] and r["html_ok"] and r["artifacts_ok"]):
            status = "FAILED"
            all_ok = False
        print(f"  {ticker}: {status} (charts={charts}, html={html}, artifacts={arts})")
        for err in r["errors"]:
            print(f"    [!] {err}")
    print()
    if all_ok:
        print("  All tickers completed successfully.")
    else:
        print("  Some tickers had failures — see [!] lines above.")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Run full rendering pipeline for one or all MVP tickers.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ticker", metavar="TICKER", help="Single ticker to run (e.g. DHG)")
    group.add_argument("--all", action="store_true", help="Run all 5 MVP tickers")
    parser.add_argument("--pdf", action="store_true", help="Also generate PDF output")
    args = parser.parse_args()

    tickers = MVP_TICKERS if args.all else [args.ticker.upper()]
    results: list[dict[str, Any]] = []

    for ticker in tickers:
        print(f"\n--- Running pipeline for {ticker} ---")
        r = run_ticker(ticker, pdf=args.pdf)
        results.append(r)
        status = "OK" if (r["charts_ok"] and r["html_ok"] and r["artifacts_ok"]) else "partial/failed"
        print(f"  {ticker}: {status} — charts={r['chart_count']}, html={r['html_ok']}, artifacts={r['artifact_count']}")

    print_summary(results)

    # Exit non-zero only if ALL tickers failed
    any_ok = any(r["charts_ok"] or r["html_ok"] or r["artifacts_ok"] for r in results)
    return 0 if any_ok else 1


if __name__ == "__main__":
    sys.exit(main())
