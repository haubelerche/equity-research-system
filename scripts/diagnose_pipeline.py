#!/usr/bin/env python
"""Diagnostic runner: exercises the full pipeline with progress visibility.

Usage:
    python scripts/diagnose_pipeline.py --ticker DHG
    python scripts/diagnose_pipeline.py --ticker DHG --dry-run
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import UTC, datetime
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


def main() -> None:
    _load_dotenv()

    parser = argparse.ArgumentParser(description="Diagnose research pipeline with full visibility.")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--dry-run", action="store_true", help="Check config and dependencies without running the pipeline.")
    args = parser.parse_args()

    ticker = args.ticker.strip().upper()

    print(f"\n{'='*70}")
    print(f"  PIPELINE DIAGNOSTIC: {ticker}")
    print(f"  Time: {datetime.now(UTC).isoformat()}")
    print(f"{'='*70}\n")

    # Phase 1: Environment checks
    print("[1/4] Checking environment...")
    checks = _check_environment()
    all_ok = True
    for name, (ok, detail) in checks.items():
        status = "OK" if ok else "MISSING"
        print(f"  {status:>7}  {name}: {detail}")
        if not ok:
            all_ok = False

    if not all_ok:
        print("\n  *** Environment checks failed. Fix the above issues first.")
        raise SystemExit(1)

    # Phase 2: Dependency checks
    print("\n[2/4] Checking dependencies...")
    deps = _check_dependencies()
    for name, (ok, detail) in deps.items():
        status = "OK" if ok else "MISSING"
        print(f"  {status:>7}  {name}: {detail}")

    # Phase 3: Database connectivity
    print("\n[3/4] Checking database...")
    db_ok, db_detail = _check_database()
    print(f"  {'OK' if db_ok else 'FAIL':>7}  database: {db_detail}")
    if not db_ok:
        print("\n  *** Database connection failed.")
        raise SystemExit(1)

    if args.dry_run:
        print("\n  Dry run complete. All checks passed.")
        return

    # Phase 4: Run the pipeline
    print(f"\n[4/4] Running full pipeline for {ticker}...")
    print("       (auto-approve-assumptions + auto-approve-final enabled)\n")

    t0 = time.monotonic()
    try:
        from scripts.run_research import parse_args, submit_harness_run
        run_args = parse_args([
            "--ticker", ticker,
            "--auto-approve-assumptions",
            "--auto-approve-final",
        ])
        run_id = submit_harness_run(run_args)
        elapsed = time.monotonic() - t0
        print(f"\n  Pipeline completed in {elapsed:.1f}s")
        print(f"  Run ID: {run_id}")

        # Check for output files
        pdf_dir = ROOT / "output" / "pdf"
        html_dir = ROOT / "output" / "html"
        pdfs = list(pdf_dir.glob(f"{ticker}_*_report.pdf")) if pdf_dir.exists() else []
        htmls = list(html_dir.glob(f"{ticker}_*_report.html")) if html_dir.exists() else []
        print(f"\n  Output files:")
        if pdfs:
            for p in pdfs:
                print(f"    PDF:  {p} ({p.stat().st_size:,} bytes)")
        else:
            print(f"    PDF:  NONE in {pdf_dir}")
        if htmls:
            for h in htmls:
                print(f"    HTML: {h} ({h.stat().st_size:,} bytes)")
        else:
            print(f"    HTML: NONE in {html_dir}")

    except Exception as exc:
        elapsed = time.monotonic() - t0
        print(f"\n  *** Pipeline FAILED after {elapsed:.1f}s: {exc}")
        raise SystemExit(1)


def _check_environment() -> dict[str, tuple[bool, str]]:
    results = {}
    for key in ["ANTHROPIC_API_KEY", "DATABASE_URL", "SUPABASE_PUBLIC_KEY", "SUPABASE_SECRET_KEY"]:
        val = os.environ.get(key, "")
        if val:
            results[key] = (True, f"set ({len(val)} chars)")
        else:
            results[key] = (False, "not set")
    return results


def _check_dependencies() -> dict[str, tuple[bool, str]]:
    results = {}
    for mod, label in [
        ("anthropic", "LLM client"),
        ("weasyprint", "PDF renderer (primary)"),
        ("jinja2", "HTML templates"),
        ("pydantic", "Data models"),
        ("psycopg2", "PostgreSQL driver"),
        ("markdown", "Markdown to HTML"),
    ]:
        try:
            __import__(mod)
            results[label] = (True, f"{mod} importable")
        except ImportError:
            results[label] = (False, f"{mod} not installed")
    return results


def _check_database() -> tuple[bool, str]:
    try:
        from backend.runtime_store import RuntimeStore
        from backend.settings import settings
        store = RuntimeStore(dsn=settings.database_url)
        store.check_schema_version()
        return True, "connected, schema valid"
    except Exception as exc:
        return False, str(exc)


if __name__ == "__main__":
    main()
