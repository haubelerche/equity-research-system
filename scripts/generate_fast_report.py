"""Render the best available report and its explanation from built run artifacts.

This script does NOT run the multi-agent pipeline, ingestion, OCR, or parsing.
Quality findings are disclosed in the report status instead of blocking export.

Target: well under 120 seconds.

Usage:
    python scripts/generate_fast_report.py --ticker DHG
    python scripts/generate_fast_report.py --ticker DHG --mode standard
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
import time
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


# --- module-level names expected by tests (patchable) ---

from backend.dataops.snapshot_freshness import latest_ready_snapshot
from backend.reporting.final_report_renderer import (
    render_client_report_to_directory,
    render_report_explanation_to_directory,
)
from backend.storage import RUNS_BUCKET, SupabaseStorageAdapter, run_artifact_key


def _latest_report_run_ids(ticker: str, mode: str = "standard") -> list[str]:
    """Return runs with enough built artifacts to render, newest first."""
    from backend.database.config import connect_with_retry, require_database_url

    with connect_with_retry(require_database_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT r.run_id
                FROM research.runs r
                JOIN research.run_artifacts a ON a.run_id = r.run_id
                WHERE r.ticker = %s
                  AND a.section_key IN (
                    'publishable_final_report_model',
                    'review_passed_report_model',
                    'report_candidate_model',
                    'valuation'
                  )
                ORDER BY r.run_id DESC
                """,
                (ticker.upper(),),
            )
            rows = cur.fetchall()
    return [row[0] for row in rows]


def generate_fast_report(ticker: str, mode: str = "standard") -> dict:
    """Render the latest report for *ticker* from existing run artifacts.

    Fails fast if there is no ready snapshot or no prior run with a built report.
    Returns a result dict with ticker, snapshot_id, run_id, elapsed_sec,
    report PDF path, and explanation PDF path.
    """
    t_start = time.monotonic()

    # 1. Require a fresh snapshot — do NOT start ingestion.
    snapshot = latest_ready_snapshot(ticker)
    if snapshot is None:
        raise SystemExit(
            f"No ready snapshot for {ticker}; run the full pipeline first."
        )

    # 2. Find the most-recent run that has a built report artifact.
    run_ids = _latest_report_run_ids(ticker, mode)
    if not run_ids:
        raise SystemExit(
            f"No prior run with a built report for {ticker}; run the full pipeline first."
        )

    # 3. Always render locally with the current renderer/chart policy. Published
    # run reports stay immutable for audit and may have been created by older code.
    output_dir = ROOT / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_dest = output_dir / f"{ticker}_report.pdf"
    explanation_dest = output_dir / f"{ticker}_explanation.pdf"
    workings_dest = output_dir / f"{ticker}_valuation_workings.md"

    storage = SupabaseStorageAdapter()
    used_run_id = None
    workings_path = None
    last_error: Exception | None = None
    for rid in run_ids:
        try:
            workings_key = run_artifact_key(rid, "report_workings.md")
            with tempfile.TemporaryDirectory(prefix=f"fast-report-{rid}-") as temp_dir:
                html_path, pdf_path, view_model = render_client_report_to_directory(
                    run_id=rid,
                    ticker=ticker,
                    mode=mode,
                    output_dir=temp_dir,
                )
                explanation_html, explanation_pdf = render_report_explanation_to_directory(
                    run_id=rid,
                    ticker=ticker,
                    view_model=view_model,
                    output_dir=temp_dir,
                )
                shutil.copy2(pdf_path, pdf_dest)
                shutil.copy2(explanation_pdf, explanation_dest)

            if storage.exists(RUNS_BUCKET, workings_key):
                storage.download_file(RUNS_BUCKET, workings_key, workings_dest)
                workings_path = str(workings_dest)

            used_run_id = rid
            break
        except Exception as exc:  # noqa: BLE001
            print(
                f"[generate_fast_report] WARNING: run_id={rid} failed to reuse or render: {exc}",
                file=sys.stderr,
            )
            last_error = exc

    if used_run_id is None:
        raise SystemExit(
            f"All candidate runs failed to reuse or render for {ticker}. Last error: {last_error}"
        )

    elapsed = time.monotonic() - t_start

    out = {
        "ticker": ticker,
        "snapshot_id": snapshot.get("snapshot_id"),
        "run_id": used_run_id,
        "elapsed_sec": round(elapsed, 2),
        "pdf_path": str(pdf_dest),
        "explanation_pdf_path": str(explanation_dest),
    }

    # The valuation workings .md is a best-effort verification companion.
    if workings_path:
        out["workings_path"] = workings_path

    print(
        f"[generate_fast_report] ticker={ticker} run_id={used_run_id} "
        f"elapsed={elapsed:.1f}s report={pdf_dest} explanation={explanation_dest}"
    )
    if elapsed > 120:
        print(
            f"[generate_fast_report] WARNING: elapsed {elapsed:.1f}s exceeds 120s target.",
            file=sys.stderr,
        )

    return out


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render the latest report from existing run artifacts (no pipeline/ingestion).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--ticker", required=True, help="Ticker symbol (e.g. DHG)")
    parser.add_argument(
        "--mode",
        default="standard",
        choices=("standard", "analyst_draft", "client_final", "internal_debug"),
        help="Use standard for the unified non-blocking report flow",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    _load_dotenv()
    args = parse_args(argv)
    generate_fast_report(args.ticker.strip().upper(), mode=args.mode)


if __name__ == "__main__":
    main()
