"""Audit research-data and PDF readiness for the configured ticker universe.

The full pipeline is expensive and failure-isolated, so operators need a cheap
post-run audit that identifies exactly which tickers still lack raw financial
data, local PDF outputs, or DB-backed renderability.

Usage:
    python scripts/audit_universe_report_readiness.py
    python scripts/audit_universe_report_readiness.py --include-db --strict
    python scripts/audit_universe_report_readiness.py --expected-count 51
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REQUIRED_BCTC_FILES = (
    "income_statement_year.json",
    "balance_sheet_year.json",
    "cash_flow_year.json",
    "ratio_year.json",
)


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


def _local_status(ticker: str, output_dir: Path) -> dict[str, Any]:
    bctc_dir = ROOT / "data" / "raw" / "bctc" / ticker
    existing_bctc = sorted(
        name for name in REQUIRED_BCTC_FILES if (bctc_dir / name).is_file()
    )
    missing_bctc = [name for name in REQUIRED_BCTC_FILES if name not in existing_bctc]
    report_path = output_dir / f"{ticker}_report.pdf"
    explanation_path = output_dir / f"{ticker}_explanation.pdf"
    return {
        "raw_bctc_dir": str(bctc_dir),
        "raw_bctc_complete": not missing_bctc,
        "raw_bctc_existing": existing_bctc,
        "raw_bctc_missing": missing_bctc,
        "has_report_pdf": report_path.is_file(),
        "has_explanation_pdf": explanation_path.is_file(),
        "report_pdf_path": str(report_path) if report_path.is_file() else None,
        "explanation_pdf_path": str(explanation_path) if explanation_path.is_file() else None,
    }


def _db_status(ticker: str, mode: str) -> dict[str, Any]:
    try:
        from backend.dataops.snapshot_freshness import latest_ready_snapshot
        from scripts.generate_fast_report import _latest_report_run_ids

        snapshot = latest_ready_snapshot(ticker)
        run_ids = _latest_report_run_ids(ticker, mode=mode)
        return {
            "db_checked": True,
            "ready_snapshot": snapshot,
            "has_ready_snapshot": snapshot is not None,
            "renderable_run_ids": run_ids,
            "has_renderable_run": bool(run_ids),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "db_checked": False,
            "db_error": str(exc),
            "has_ready_snapshot": False,
            "has_renderable_run": False,
            "renderable_run_ids": [],
        }


def audit_universe(
    *,
    output_dir: Path,
    include_db: bool = False,
    mode: str = "analyst_draft",
    exclude_tickers: set[str] | None = None,
    recommend_limit: int = 0,
) -> dict[str, Any]:
    from backend.dataset.config_io import load_universe_rows

    excluded = {ticker.strip().upper() for ticker in (exclude_tickers or set()) if ticker.strip()}
    rows = load_universe_rows()
    records: list[dict[str, Any]] = []
    for row in rows:
        ticker = str(row.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        if ticker in excluded:
            continue
        local = _local_status(ticker, output_dir)
        db = _db_status(ticker, mode) if include_db else {
            "db_checked": False,
            "has_ready_snapshot": False,
            "has_renderable_run": False,
            "renderable_run_ids": [],
        }
        local_pdf_ready = bool(local["has_report_pdf"] and local["has_explanation_pdf"])
        db_exportable = bool(db["has_ready_snapshot"] and db["has_renderable_run"])
        records.append(
            {
                "ticker": ticker,
                "company_name": row.get("company_name") or "",
                "exchange": row.get("exchange") or "",
                "segment": row.get("segment") or "",
                **local,
                **db,
                "local_pdf_ready": local_pdf_ready,
                "exportable": local_pdf_ready or db_exportable,
                "release_readiness_score": _release_readiness_score(
                    raw_bctc_complete=bool(local["raw_bctc_complete"]),
                    local_pdf_ready=local_pdf_ready,
                    has_ready_snapshot=bool(db["has_ready_snapshot"]),
                    has_renderable_run=bool(db["has_renderable_run"]),
                ),
            }
        )

    candidates = sorted(
        records,
        key=lambda r: (
            int(bool(r["exportable"])),
            int(bool(r["raw_bctc_complete"])),
            int(bool(r["local_pdf_ready"])),
            int(bool(r["has_ready_snapshot"])),
            int(bool(r["has_renderable_run"])),
            int(r["release_readiness_score"]),
        ),
        reverse=True,
    )
    recommended = candidates[:recommend_limit] if recommend_limit > 0 else []
    summary = {
        "universe_count": len(records),
        "excluded_tickers": sorted(excluded),
        "raw_bctc_complete_count": sum(1 for r in records if r["raw_bctc_complete"]),
        "local_pdf_ready_count": sum(1 for r in records if r["local_pdf_ready"]),
        "exportable_count": sum(1 for r in records if r["exportable"]),
        "recommended_release_candidates": [
            {
                "ticker": r["ticker"],
                "score": r["release_readiness_score"],
                "raw_bctc_complete": r["raw_bctc_complete"],
                "local_pdf_ready": r["local_pdf_ready"],
                "has_ready_snapshot": r["has_ready_snapshot"],
                "has_renderable_run": r["has_renderable_run"],
                "exportable": r["exportable"],
            }
            for r in recommended
        ],
        "missing_raw_bctc": [r["ticker"] for r in records if not r["raw_bctc_complete"]],
        "missing_local_pdf": [r["ticker"] for r in records if not r["local_pdf_ready"]],
        "not_exportable": [r["ticker"] for r in records if not r["exportable"]],
    }
    return {"summary": summary, "records": records}


def _release_readiness_score(
    *,
    raw_bctc_complete: bool,
    local_pdf_ready: bool,
    has_ready_snapshot: bool,
    has_renderable_run: bool,
) -> int:
    score = 0
    if raw_bctc_complete:
        score += 40
    if local_pdf_ready:
        score += 35
    if has_ready_snapshot:
        score += 15
    if has_renderable_run:
        score += 10
    return score


def _print_summary(result: dict[str, Any]) -> None:
    summary = result["summary"]
    print(
        "[audit] universe={universe_count} raw_bctc={raw_bctc_complete_count} "
        "local_pdf={local_pdf_ready_count} exportable={exportable_count}".format(**summary)
    )
    if summary.get("excluded_tickers"):
        print(f"[audit] excluded: {','.join(summary['excluded_tickers'])}")
    if summary.get("recommended_release_candidates"):
        tickers = ",".join(item["ticker"] for item in summary["recommended_release_candidates"])
        print(f"[audit] recommended_release_candidates: {tickers}")
    for key in ("missing_raw_bctc", "missing_local_pdf", "not_exportable"):
        values = summary[key]
        if values:
            print(f"[audit] {key}: {','.join(values)}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit universe-level research data and PDF readiness.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--output-dir", default="output", help="Directory containing local PDFs.")
    parser.add_argument("--include-db", action="store_true", help="Check ready snapshots and renderable run artifacts in DB.")
    parser.add_argument(
        "--mode",
        default="analyst_draft",
        choices=("standard", "analyst_draft", "client_final", "internal_debug"),
        help="Render mode used when checking DB-backed renderability.",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Ticker to exclude from release-readiness accounting. Repeatable or comma-separated.",
    )
    parser.add_argument(
        "--recommend-limit",
        type=int,
        default=0,
        help="Emit the top N release candidates ranked by current readiness.",
    )
    parser.add_argument("--write-json", default="", help="Optional path for a JSON audit artifact.")
    parser.add_argument("--expected-count", type=int, help="Fail if universe row count differs.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero unless every ticker is exportable.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    _load_dotenv()
    args = parse_args(argv)
    result = audit_universe(
        output_dir=(ROOT / args.output_dir).resolve(),
        include_db=args.include_db,
        mode=args.mode,
        exclude_tickers=_parse_exclusions(args.exclude),
        recommend_limit=max(0, int(args.recommend_limit or 0)),
    )
    _print_summary(result)
    if args.write_json:
        out = Path(args.write_json)
        if not out.is_absolute():
            out = ROOT / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        print(f"[audit] wrote {out}")
    count = result["summary"]["universe_count"]
    if args.expected_count is not None and count != args.expected_count:
        print(
            f"[audit] expected-count mismatch: expected={args.expected_count} actual={count}",
            file=sys.stderr,
        )
        return 2
    if args.strict and result["summary"]["not_exportable"]:
        return 1
    return 0


def _parse_exclusions(values: list[str]) -> set[str]:
    exclusions: set[str] = set()
    for value in values:
        for item in value.split(","):
            ticker = item.strip().upper()
            if ticker:
                exclusions.add(ticker)
    return exclusions


if __name__ == "__main__":
    raise SystemExit(main())
