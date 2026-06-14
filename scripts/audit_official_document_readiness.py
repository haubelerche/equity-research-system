"""Audit official PDF/OCR readiness for the configured ticker universe.

This is a cheap local filesystem audit. It does not fetch PDFs, run OCR, or
write to the database.

Usage:
    python scripts/audit_official_document_readiness.py --from-year 2022 --to-year 2025
    python scripts/audit_official_document_readiness.py --from-year 2022 --to-year 2025 --strict
    python scripts/audit_official_document_readiness.py --from-year 2022 --to-year 2025 --write-json output/official_document_readiness.json
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OFFICIAL_DOCS_DIR = ROOT / "data" / "official_documents"
OCR_ARTIFACTS_DIR = ROOT / "storage" / "sources" / "ocr_artifacts"


def _has_nonempty_csv(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        with path.open(encoding="utf-8-sig", newline="") as fh:
            return any((row.get("metric_id") or "").strip() for row in csv.DictReader(fh))
    except Exception:
        return False


def _latest_ocr_metadata(ticker: str, year: int) -> dict[str, Any] | None:
    root = OCR_ARTIFACTS_DIR / ticker / str(year)
    if not root.is_dir():
        return None
    metas = sorted(root.glob("*/metadata.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not metas:
        return None
    try:
        data = json.loads(metas[0].read_text(encoding="utf-8"))
        data["_metadata_path"] = str(metas[0])
        return data
    except Exception:
        return {"status": "unreadable", "_metadata_path": str(metas[0])}


def audit_official_documents(from_year: int, to_year: int) -> dict[str, Any]:
    from backend.dataset.config_io import load_universe_rows

    years = list(range(from_year, to_year + 1))
    records: list[dict[str, Any]] = []
    for row in load_universe_rows():
        ticker = str(row.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        for year in years:
            year_dir = OFFICIAL_DOCS_DIR / ticker / str(year)
            pdf_path = year_dir / "source_document.pdf"
            metadata_path = year_dir / "metadata.json"
            extracted_path = year_dir / "extracted_facts.csv"
            extracted_ocr_path = year_dir / "extracted_facts_ocr.csv"
            ocr_meta = _latest_ocr_metadata(ticker, year)
            ocr_status = str((ocr_meta or {}).get("status") or "")
            ocr_pages = int((ocr_meta or {}).get("pages_processed") or 0)
            record = {
                "ticker": ticker,
                "company_name": row.get("company_name") or "",
                "exchange": row.get("exchange") or "",
                "segment": row.get("segment") or "",
                "fiscal_year": year,
                "year_dir_exists": year_dir.is_dir(),
                "has_metadata": metadata_path.is_file(),
                "has_source_pdf": pdf_path.is_file(),
                "source_pdf_path": str(pdf_path) if pdf_path.is_file() else None,
                "has_extracted_facts": _has_nonempty_csv(extracted_path),
                "has_ocr_extracted_facts": _has_nonempty_csv(extracted_ocr_path),
                "has_ocr_artifact": ocr_meta is not None,
                "ocr_status": ocr_status or None,
                "ocr_pages_processed": ocr_pages,
                "ocr_metadata_path": (ocr_meta or {}).get("_metadata_path"),
            }
            record["official_research_ready"] = bool(
                record["has_source_pdf"]
                and (record["has_extracted_facts"] or record["has_ocr_extracted_facts"])
            )
            record["ocr_ready"] = bool(
                record["has_ocr_artifact"]
                and ocr_status == "completed"
                and ocr_pages > 0
            )
            records.append(record)

    missing_pdf = [r for r in records if not r["has_source_pdf"]]
    missing_extraction = [
        r for r in records
        if r["has_source_pdf"] and not (r["has_extracted_facts"] or r["has_ocr_extracted_facts"])
    ]
    not_ready = [r for r in records if not r["official_research_ready"]]
    summary = {
        "ticker_count": len({r["ticker"] for r in records}),
        "year_count": len(years),
        "expected_document_slots": len(records),
        "source_pdf_count": sum(1 for r in records if r["has_source_pdf"]),
        "extracted_facts_count": sum(
            1 for r in records if r["has_extracted_facts"] or r["has_ocr_extracted_facts"]
        ),
        "ocr_ready_count": sum(1 for r in records if r["ocr_ready"]),
        "official_research_ready_count": sum(1 for r in records if r["official_research_ready"]),
        "missing_pdf_count": len(missing_pdf),
        "missing_extraction_count": len(missing_extraction),
        "not_ready_count": len(not_ready),
        "tickers_not_ready": sorted({r["ticker"] for r in not_ready}),
        "missing_pdf": [{"ticker": r["ticker"], "fiscal_year": r["fiscal_year"]} for r in missing_pdf],
        "missing_extraction": [
            {"ticker": r["ticker"], "fiscal_year": r["fiscal_year"]}
            for r in missing_extraction
        ],
    }
    return {"summary": summary, "records": records}


def _print_summary(result: dict[str, Any]) -> None:
    s = result["summary"]
    print(
        "[official-audit] tickers={ticker_count} years={year_count} slots={expected_document_slots} "
        "pdf={source_pdf_count} extracted={extracted_facts_count} ocr_ready={ocr_ready_count} "
        "ready={official_research_ready_count} not_ready={not_ready_count}".format(**s)
    )
    if s["tickers_not_ready"]:
        print("[official-audit] tickers_not_ready: " + ",".join(s["tickers_not_ready"]))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit official PDF/OCR readiness.")
    parser.add_argument("--from-year", type=int, required=True, dest="from_year")
    parser.add_argument("--to-year", type=int, required=True, dest="to_year")
    parser.add_argument("--write-json", default="")
    parser.add_argument("--expected-tickers", type=int)
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = audit_official_documents(args.from_year, args.to_year)
    _print_summary(result)
    if args.write_json:
        out = Path(args.write_json)
        if not out.is_absolute():
            out = ROOT / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[official-audit] wrote {out}")
    if args.expected_tickers is not None and result["summary"]["ticker_count"] != args.expected_tickers:
        print(
            "[official-audit] expected ticker mismatch: "
            f"expected={args.expected_tickers} actual={result['summary']['ticker_count']}",
            file=sys.stderr,
        )
        return 2
    if args.strict and result["summary"]["not_ready_count"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
