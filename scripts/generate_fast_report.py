"""Fast report path: render viewable PDF/HTML from the latest already-built run artifacts.

This script does NOT run the multi-agent pipeline, ingestion, OCR, parsing,
indexing, or any blocking review gates. It reads existing persisted artifacts
and renders them using the ClientReportPublisher.

Target: well under 120 seconds.

Usage:
    python scripts/generate_fast_report.py --ticker DHG
    python scripts/generate_fast_report.py --ticker DHG --mode client_final
"""
from __future__ import annotations

import argparse
import os
import sys
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
from backend.reporting.final_report_renderer import ClientReportPublisher
from backend.storage import SupabaseStorageAdapter


def _latest_report_run_ids(ticker: str) -> list[str]:
    """Return run_ids for *ticker* that have a built final_report_model, newest first."""
    from backend.database.config import connect_with_retry, require_database_url

    with connect_with_retry(require_database_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT run_id FROM research.run_artifacts "
                "WHERE run_id LIKE %s AND section_key = 'final_report_model' "
                "ORDER BY run_id DESC",
                (f"run_{ticker.lower()}%",),
            )
            rows = cur.fetchall()
    return [row[0] for row in rows]


def generate_fast_report(ticker: str, mode: str = "client_final") -> dict:
    """Render the latest report for *ticker* from existing run artifacts.

    Fails fast if there is no ready snapshot or no prior run with a built report.
    Returns a result dict with ticker, snapshot_id, run_id, elapsed_sec,
    pdf_path, and html_path.
    """
    t_start = time.monotonic()

    # 1. Require a fresh snapshot — do NOT start ingestion.
    snapshot = latest_ready_snapshot(ticker)
    if snapshot is None:
        raise SystemExit(
            f"No ready snapshot for {ticker}; run the full pipeline first."
        )

    # 2. Find the most-recent run that has a built report artifact.
    run_ids = _latest_report_run_ids(ticker)
    if not run_ids:
        raise SystemExit(
            f"No prior run with a built report for {ticker}; run the full pipeline first."
        )

    # 3. Try each candidate run_id newest-first; use the first that succeeds.
    published = None
    used_run_id = None
    last_error: Exception | None = None
    for rid in run_ids:
        try:
            published = ClientReportPublisher().publish(run_id=rid, ticker=ticker, mode=mode)
            used_run_id = rid
            break
        except Exception as exc:  # noqa: BLE001
            print(f"[generate_fast_report] WARNING: run_id={rid} failed to render: {exc}", file=sys.stderr)
            last_error = exc

    if published is None or used_run_id is None:
        raise SystemExit(
            f"All candidate runs failed to render for {ticker}. Last error: {last_error}"
        )

    # 4. Download rendered files to output/.
    output_dir = ROOT / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    result_dict = published.to_dict()
    pdf_ref = result_dict["pdf"]
    html_ref = result_dict["html"]

    pdf_dest = output_dir / f"{ticker}_fast_report.pdf"
    html_dest = output_dir / f"{ticker}_fast_report.html"

    storage = SupabaseStorageAdapter()
    storage.download_file(pdf_ref["storage_bucket"], pdf_ref["storage_path"], pdf_dest)
    storage.download_file(html_ref["storage_bucket"], html_ref["storage_path"], html_dest)

    elapsed = time.monotonic() - t_start

    out = {
        "ticker": ticker,
        "snapshot_id": snapshot.get("snapshot_id"),
        "run_id": used_run_id,
        "elapsed_sec": round(elapsed, 2),
        "pdf_path": str(pdf_dest),
        "html_path": str(html_dest),
    }

    # The valuation workings .md is a best-effort verification companion: download
    # it next to the PDF when the publisher produced one.
    workings_ref = result_dict.get("workings_md")
    if workings_ref:
        workings_dest = output_dir / f"{ticker}_valuation_workings.md"
        storage.download_file(
            workings_ref["storage_bucket"], workings_ref["storage_path"], workings_dest
        )
        out["workings_path"] = str(workings_dest)

    print(
        f"[generate_fast_report] ticker={ticker} run_id={used_run_id} "
        f"elapsed={elapsed:.1f}s pdf={pdf_dest} html={html_dest}"
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
        default="client_final",
        help="Render mode passed to ClientReportPublisher.publish()",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    _load_dotenv()
    args = parse_args(argv)
    generate_fast_report(args.ticker.strip().upper(), mode=args.mode)


if __name__ == "__main__":
    main()
