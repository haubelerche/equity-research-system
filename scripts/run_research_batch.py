"""Batch entrypoint: run the full research pipeline across many tickers (scale to 53).

Each ticker runs as an ISOLATED subprocess (scripts/run_research.py), so a crash in one
ticker's heavy pipeline (OCR / agents / valuation) cannot take down the batch. Failure-
isolated and resumable (--resume skips tickers that already have a built report).
Every successful or resumed ticker is then exported into a report PDF and explanation PDF.

This is the expensive tier — OCR + multi-agent LLM + valuation PER ticker. Stage it
(start with a few tickers) and watch cost/time before running the full universe.

Usage:
    python scripts/run_research_batch.py --tickers DHG IMP --draft
    python scripts/run_research_batch.py --all --resume --draft --dry-run
    python scripts/run_research_batch.py --all --resume --draft --max-tickers 5
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_dotenv() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _make_run_one(passthrough: list[str]):
    """Return run_one(ticker) that runs scripts/run_research.py as an isolated subprocess."""
    script = str(ROOT / "scripts" / "run_research.py")

    def run_one(ticker: str) -> dict:
        cmd = [sys.executable, script, "--ticker", ticker, *passthrough]
        print(f"[batch] >>> {ticker}: {' '.join(cmd[2:])}", flush=True)
        proc = subprocess.run(cmd, cwd=str(ROOT))  # streams output; isolated process
        if proc.returncode != 0:
            raise RuntimeError(f"run_research exited {proc.returncode}")
        return {"returncode": 0}

    return run_one


def _make_should_skip():
    """Skip tickers that already have a built (locked) report run."""
    from scripts.generate_fast_report import _latest_report_run_ids

    def should_skip(ticker: str) -> bool:
        try:
            return bool(_latest_report_run_ids(ticker, mode="analyst_draft"))
        except Exception:  # noqa: BLE001 — if the check fails, don't skip (safer to attempt)
            return False

    return should_skip


def main(argv: list[str] | None = None) -> int:
    _load_dotenv()
    from backend.pipeline_batch import run_pipeline_for_tickers

    parser = argparse.ArgumentParser(description="Run the full research pipeline for many tickers.")
    parser.add_argument("--tickers", nargs="*", default=[], help="Tickers (space/comma).")
    parser.add_argument("--all", action="store_true", help="Run the full 53-ticker universe.")
    parser.add_argument("--resume", action="store_true", help="Skip tickers with a built report.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print selected tickers and the per-ticker command without running the pipeline.",
    )
    parser.add_argument(
        "--max-tickers",
        type=int,
        help="Cap this invocation after ticker selection; use for staged rollout.",
    )
    parser.add_argument("--from-year", type=int, help="Passthrough to run_research.")
    parser.add_argument("--to-year", type=int, help="Passthrough to run_research.")
    parser.add_argument("--ocr", action="store_true", help="Passthrough: enable OCR.")
    parser.add_argument("--draft", action="store_true", help="Passthrough: draft auto-approve mode.")
    args = parser.parse_args(argv)

    if args.all:
        from backend.reporting.report_data_loader import _COMPANIES

        tickers = sorted(_COMPANIES)
    else:
        tickers = [t.strip().upper() for e in args.tickers for t in str(e).split(",") if t.strip()]
    if not tickers:
        parser.error("provide --tickers or --all")
    if args.max_tickers is not None:
        if args.max_tickers < 1:
            parser.error("--max-tickers must be at least 1")

    passthrough: list[str] = []
    if args.from_year is not None:
        passthrough += ["--from-year", str(args.from_year)]
    if args.to_year is not None:
        passthrough += ["--to-year", str(args.to_year)]
    if args.ocr:
        passthrough.append("--ocr")
    if args.draft:
        passthrough.append("--draft")

    if args.dry_run:
        preview_tickers = tickers[: args.max_tickers]
        command = " ".join(
            ["python", "scripts/run_research.py", "--ticker", "<TICKER>", *passthrough]
        )
        print(
            f"[batch] dry-run: selected={len(preview_tickers)} "
            f"tickers={','.join(preview_tickers)}"
        )
        print(f"[batch] per-ticker command: {command}")
        print("[batch] export command: python scripts/generate_fast_report.py --ticker <TICKER>")
        return 0

    should_skip = _make_should_skip() if args.resume else None
    results = run_pipeline_for_tickers(
        tickers,
        run_one=_make_run_one(passthrough),
        should_skip=should_skip,
        max_runs=args.max_tickers,
    )

    ok = sum(1 for r in results if r["status"] == "ok")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    errors = [r for r in results if r["status"] == "error"]
    export_errors: list[dict[str, str]] = []
    export_script = str(ROOT / "scripts" / "generate_fast_report.py")
    for result in results:
        if result["status"] not in {"ok", "skipped"}:
            continue
        ticker = str(result["ticker"])
        print(f"[batch] >>> export {ticker}: report PDF + explanation PDF", flush=True)
        proc = subprocess.run(
            [sys.executable, export_script, "--ticker", ticker],
            cwd=str(ROOT),
        )
        if proc.returncode != 0:
            export_errors.append({"ticker": ticker, "error": f"report export exited {proc.returncode}"})

    print(f"\n[batch] done: ok={ok} skipped={skipped} error={len(errors)} / {len(results)}")
    for r in errors:
        print(f"[batch] FAILED {r['ticker']}: {r['error']}", file=sys.stderr)
    for r in export_errors:
        print(f"[batch] EXPORT FAILED {r['ticker']}: {r['error']}", file=sys.stderr)
    return 1 if errors or export_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
