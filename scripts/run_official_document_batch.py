"""Batch official-document PDF discovery/extraction/OCR for the universe.

Each ticker is executed in an isolated subprocess through
scripts/auto_ingest_official_documents.py so one ticker failure does not abort
the full configured-universe job.

Usage:
    python scripts/run_official_document_batch.py --all --from-year 2022 --to-year 2025 --ocr --dry-run
    python scripts/run_official_document_batch.py --all --from-year 2022 --to-year 2025 --ocr --resume
    python scripts/run_official_document_batch.py --tickers DHG MKP --from-year 2022 --to-year 2025 --ocr
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "official_sources"


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


def _configured_universe_tickers() -> list[str]:
    from backend.dataset.config_io import load_universe_tickers

    return load_universe_tickers()


def _complete_tickers(from_year: int, to_year: int) -> set[str]:
    from scripts.audit_official_document_readiness import audit_official_documents

    result = audit_official_documents(from_year, to_year)
    expected = to_year - from_year + 1
    grouped: dict[str, list[dict]] = {}
    for row in result["records"]:
        grouped.setdefault(str(row["ticker"]), []).append(row)
    return {
        ticker
        for ticker, rows in grouped.items()
        if len(rows) == expected and all(r["official_research_ready"] for r in rows)
    }


def _select_tickers(args: argparse.Namespace) -> list[str]:
    if args.all:
        return _configured_universe_tickers()
    return [t.strip().upper() for e in args.tickers for t in str(e).split(",") if t.strip()]


def _export_golden_for_ticker(ticker: str) -> int:
    """Export this ticker's OCR facts to its golden CSV (benchmark dataset). Best-effort.

    Returns the number of fact rows exported (0 if no OCR artifacts or on error).
    """
    try:
        from scripts.extract_facts_from_ocr import run_for_ticker

        rows = run_for_ticker(ticker)
        return len(rows)
    except Exception as exc:  # noqa: BLE001 — golden export is observability, never fatal
        print(f"[official-batch] golden export failed for {ticker}: {exc}", file=sys.stderr)
        return 0


def _write_cohort_coverage_report(tickers: list[str], from_year: int, to_year: int) -> Path | None:
    """Aggregate per-ticker auto_ingest JSON results into an honest cohort coverage report."""
    from backend.dataops.ocr_coverage import (
        cohort_summary,
        coverage_from_payload,
        render_cohort_markdown,
    )

    coverages = []
    for ticker in tickers:
        json_path = ARTIFACT_DIR / f"{ticker}_auto_ingest_result.json"
        if not json_path.exists():
            continue
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        coverages.append(coverage_from_payload(payload))

    if not coverages:
        print("[official-batch] no per-ticker JSON results found — skipping cohort report")
        return None

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    md_path = ARTIFACT_DIR / "ocr_coverage_report.md"
    json_path = ARTIFACT_DIR / "ocr_coverage_report.json"
    md_path.write_text(
        render_cohort_markdown(coverages, from_year=from_year, to_year=to_year),
        encoding="utf-8",
    )
    json_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(UTC).isoformat(),
                "from_year": from_year,
                "to_year": to_year,
                "summary": cohort_summary(coverages),
                "tickers": [c.to_dict() for c in coverages],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    summary = cohort_summary(coverages)
    print(
        f"[official-batch] cohort coverage: "
        f"official_or_ocr={summary['by_status']['official_or_ocr']} "
        f"pdf_found_no_facts={summary['by_status']['pdf_found_no_facts']} "
        f"no_source_pdf={summary['by_status']['no_source_pdf']} "
        f"/ {summary['tickers']} tickers; ocr_promoted={summary['ocr_promoted']}"
    )
    print(f"[official-batch] cohort report: {md_path}")
    return md_path


def main(argv: list[str] | None = None) -> int:
    _load_dotenv()
    parser = argparse.ArgumentParser(
        description="Batch official document ingest/OCR for many tickers.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--tickers", nargs="*", default=[])
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--from-year", type=int, required=True, dest="from_year")
    parser.add_argument("--to-year", type=int, required=True, dest="to_year")
    parser.add_argument("--channels", default="cafef,pdf")
    parser.add_argument("--min-pdf-confidence", type=float, default=0.6, dest="min_pdf_confidence")
    parser.add_argument("--ocr", action="store_true", help="Enable OCR for scanned PDFs.")
    parser.add_argument(
        "--promote-official-only",
        action="store_true",
        help="Pass through explicit official-only promotion for reviewed runs.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Pass dry-run to per-ticker ingest.")
    parser.add_argument("--resume", action="store_true", help="Skip tickers already complete locally.")
    parser.add_argument("--max-tickers", type=int)
    parser.add_argument("--expected-count", type=int)
    args = parser.parse_args(argv)

    tickers = _select_tickers(args)
    if not tickers:
        parser.error("provide --tickers or --all")
    if args.expected_count is not None and len(tickers) != args.expected_count:
        parser.error(f"selected ticker count mismatch: expected {args.expected_count}, got {len(tickers)}")
    if args.max_tickers is not None and args.max_tickers < 1:
        parser.error("--max-tickers must be at least 1")

    script = ROOT / "scripts" / "auto_ingest_official_documents.py"
    selected = tickers[: args.max_tickers] if args.max_tickers else tickers
    print(
        f"[official-batch] selected={len(selected)} "
        f"range={args.from_year}-{args.to_year} tickers={','.join(selected)}"
    )

    results: list[dict[str, str]] = []
    complete_tickers = _complete_tickers(args.from_year, args.to_year) if args.resume else set()
    for ticker in selected:
        if ticker in complete_tickers:
            print(f"[official-batch] skip {ticker}: complete")
            results.append({"ticker": ticker, "status": "skipped"})
            continue
        cmd = [
            sys.executable,
            str(script),
            "--ticker",
            ticker,
            "--from-year",
            str(args.from_year),
            "--to-year",
            str(args.to_year),
            "--channels",
            args.channels,
            "--min-pdf-confidence",
            str(args.min_pdf_confidence),
        ]
        if args.ocr:
            cmd.append("--ocr")
        if args.promote_official_only:
            cmd.append("--promote-official-only")
        if args.dry_run:
            cmd.append("--dry-run")
        print(f"[official-batch] >>> {ticker}: {' '.join(cmd[2:])}", flush=True)
        proc = subprocess.run(cmd, cwd=str(ROOT))
        if proc.returncode == 0:
            results.append({"ticker": ticker, "status": "ok"})
        else:
            results.append({"ticker": ticker, "status": "error", "error": f"exit={proc.returncode}"})

        # Export this ticker's OCR facts to its golden CSV so the data-quality
        # benchmark (official_reconciliation_rate) sees OCR coverage. Real runs only.
        if args.ocr and not args.dry_run:
            exported = _export_golden_for_ticker(ticker)
            if exported:
                print(f"[official-batch] {ticker}: exported {exported} OCR facts to golden CSV")

    ok = sum(1 for r in results if r["status"] == "ok")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    errors = [r for r in results if r["status"] == "error"]
    print(f"[official-batch] done: ok={ok} skipped={skipped} error={len(errors)} / {len(results)}")
    for error in errors:
        print(f"[official-batch] FAILED {error['ticker']}: {error['error']}", file=sys.stderr)

    # Honest cohort coverage report across all selected tickers.
    if not args.dry_run:
        _write_cohort_coverage_report(selected, args.from_year, args.to_year)

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
