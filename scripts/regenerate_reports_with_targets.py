"""Regenerate the client report PDFs with the relative-valuation fallback target.

For each ticker this:
  1. rebuilds facts + valuation (with the offline peer-P/E pack) + forecast + manifest
     via the same backfill path the renderer reads, persisting a fresh run; then
  2. renders that run straight to output/<TICKER>_report.pdf (+ _explanation.pdf),
     applying the current policy (RELATIVE_PE fallback, ±40% market-sanity band).

No vnstock crawl, no OCR, no agent graph — peer prices come from the collected
data/manual/market_prices.csv. Run after the valuation/policy changes so every
report shows a defensible target instead of a blank or a clamped-to-market number.

Usage:
    python scripts/regenerate_reports_with_targets.py --tickers DHG,DBD
    python scripts/regenerate_reports_with_targets.py --all
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
import tempfile
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


def _universe_tickers() -> list[str]:
    path = ROOT / "config" / "dataset" / "universe" / "pharma_vn_universe.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        return [
            str(row.get("ticker") or "").strip().upper()
            for row in csv.DictReader(handle)
            if str(row.get("ticker") or "").strip()
        ]


def _money(value: object) -> object:
    return getattr(value, "amount", value)


def _upload_to_exports(ticker: str) -> list[str]:
    """Upload output/<TICKER>_{report,explanation}.pdf to the Supabase exports bucket.

    The deployed API serves report files preferentially from EXPORTS_BUCKET (durable,
    survives Railway's ephemeral disk), so a report only appears on the Vercel
    frontend once its PDF lives there under the ticker-stable key.
    """
    from backend.storage import EXPORTS_BUCKET, SupabaseStorageAdapter, client_report_key
    from backend.reporting.pdf_quality_gate import is_client_pdf_safe

    ticker = ticker.upper()
    out_dir = ROOT / "output"
    storage = SupabaseStorageAdapter()
    uploaded: list[str] = []
    for local_name, export_name in (
        (f"{ticker}_report.pdf", "report.pdf"),
        (f"{ticker}_explanation.pdf", "explanation.pdf"),
    ):
        local_path = out_dir / local_name
        if not local_path.is_file() or not is_client_pdf_safe(local_path):
            continue
        storage.upload_file(
            EXPORTS_BUCKET,
            client_report_key(ticker, export_name),
            local_path,
            "application/pdf",
            upsert=True,
        )
        uploaded.append(export_name)
    return uploaded


def regenerate_ticker(ticker: str, *, from_year: int, to_year: int, mode: str) -> dict:
    from scripts.backfill_renderable_reports import backfill_ticker
    from backend.reporting.final_report_renderer import (
        render_client_report_to_directory,
        render_report_explanation_to_directory,
    )

    ticker = ticker.upper()
    out_dir = ROOT / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Recompute facts + valuation (peer-backed) + forecast + manifest; no render here.
    backfilled = backfill_ticker(
        ticker,
        from_year=from_year,
        to_year=to_year,
        render=False,
        auto_approve_assumptions=False,
    )
    if backfilled.get("status") == "failed":
        return {"ticker": ticker, "status": "failed", "stage": "backfill", "error": backfilled.get("error")}
    run_id = backfilled["run_id"]

    # 2. Render that run straight to output/<TICKER>_report.pdf.
    with tempfile.TemporaryDirectory(prefix=f"regen-{ticker}-") as temp_dir:
        _html, pdf_path, view_model = render_client_report_to_directory(
            run_id=run_id, ticker=ticker, mode=mode, output_dir=temp_dir
        )
        _ehtml, explanation_pdf = render_report_explanation_to_directory(
            run_id=run_id, ticker=ticker, view_model=view_model, output_dir=temp_dir
        )
        shutil.copy2(pdf_path, out_dir / f"{ticker}_report.pdf")
        shutil.copy2(explanation_pdf, out_dir / f"{ticker}_explanation.pdf")

    # Push to the durable exports bucket so the deployed API (and Vercel) serve it.
    uploaded = _upload_to_exports(ticker)

    return {
        "ticker": ticker,
        "status": "ok",
        "run_id": run_id,
        "current_price": _money(getattr(view_model, "current_price", None)),
        "target_price": _money(getattr(view_model, "target_price", None)),
        "recommendation": getattr(view_model, "recommendation", None),
        "method": getattr(view_model, "headline_valuation_method", None),
        "exports_uploaded": uploaded,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    from backend.period_scope import DEFAULT_FROM_YEAR, DEFAULT_TO_YEAR

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", help="Comma-separated tickers, e.g. DHG,DBD.")
    parser.add_argument("--all", action="store_true", help="Process the configured universe.")
    parser.add_argument("--from-year", type=int, default=DEFAULT_FROM_YEAR, dest="from_year")
    parser.add_argument("--to-year", type=int, default=DEFAULT_TO_YEAR, dest="to_year")
    parser.add_argument("--mode", default="standard")
    parser.add_argument(
        "--upload-only",
        action="store_true",
        help="Skip recompute/render; just upload existing output/<T> PDFs to the exports bucket.",
    )
    parser.add_argument("--limit", type=int, default=0, help="Optional maximum tickers to process.")
    parser.add_argument("--write-json", default="output/regenerate_reports_with_targets.json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    _load_dotenv()
    args = parse_args(argv)
    if args.all:
        tickers = _universe_tickers()
    elif args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    else:
        raise SystemExit("Provide --tickers A,B,C or --all.")
    if args.limit:
        tickers = tickers[: args.limit]

    results: list[dict] = []
    for ticker in tickers:
        try:
            if args.upload_only:
                uploaded = _upload_to_exports(ticker)
                result = {
                    "ticker": ticker.upper(),
                    "status": "ok" if uploaded else "failed",
                    "exports_uploaded": uploaded,
                    "error": None if uploaded else "no local PDF to upload",
                }
            else:
                result = regenerate_ticker(
                    ticker, from_year=args.from_year, to_year=args.to_year, mode=args.mode
                )
        except Exception as exc:  # noqa: BLE001 — keep the batch going; record the failure
            result = {"ticker": ticker.upper(), "status": "failed", "stage": "render", "error": repr(exc)}
        results.append(result)
        print(
            f"[regen] {result.get('ticker'):<5} {result.get('status'):<7} "
            f"target={result.get('target_price')} rec={result.get('recommendation')} "
            f"method={result.get('method')} exports={result.get('exports_uploaded')} "
            f"{result.get('error') or ''}"
        )

    out_path = ROOT / args.write_json
    out_path.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "total": len(results),
        "ok": sum(1 for r in results if r.get("status") == "ok"),
        "failed": sum(1 for r in results if r.get("status") == "failed"),
        "results": results,
    }
    out_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"[regen] wrote {out_path} — ok={summary['ok']} failed={summary['failed']}")
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
