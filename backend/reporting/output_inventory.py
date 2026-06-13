from __future__ import annotations

import csv as _csv
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

_PREVIEW_RE = re.compile(r"_report_page_(\d+)\.png$")


@dataclass
class ReportInventoryItem:
    ticker: str
    company_name: str
    exchange: str
    segment: str
    is_mvp: bool
    has_report: bool
    has_explanation: bool
    preview_pages: list[int] = field(default_factory=list)
    report_size: int | None = None
    updated_at: str | None = None


class _ResolvedFiles(TypedDict):
    report: Path | None
    explanation: Path | None
    preview_pages: list[int]


def _resolve_report_files(ticker: str, output_dir: Path) -> _ResolvedFiles:
    """Single point that maps a ticker to its on-disk artifacts.

    Current convention: ``{TICKER}_report.pdf`` / ``{TICKER}_explanation.pdf`` and
    ``pdf_preview/{TICKER}_report_page_{n}.png``. If a later phase introduces an
    artifact_manifest or run_id-based filenames, change ONLY this function — the
    endpoint shapes and the frontend stay untouched.
    """
    report = output_dir / f"{ticker}_report.pdf"
    explanation = output_dir / f"{ticker}_explanation.pdf"
    preview_dir = output_dir / "pdf_preview"
    pages: list[int] = []
    if preview_dir.is_dir():
        prefix = f"{ticker}_report_page_"
        for entry in preview_dir.iterdir():
            if entry.is_file() and entry.name.startswith(prefix):
                m = _PREVIEW_RE.search(entry.name)
                if m:
                    pages.append(int(m.group(1)))
    return _ResolvedFiles(
        report=report if report.is_file() else None,
        explanation=explanation if explanation.is_file() else None,
        preview_pages=sorted(pages),  # numeric order
    )


def load_universe(csv_path: Path) -> list[dict]:
    rows: list[dict] = []
    with open(csv_path, newline="", encoding="utf-8") as fh:
        for r in _csv.DictReader(fh):
            rows.append(
                {
                    "ticker": (r.get("ticker") or "").strip().upper(),
                    "company_name": (r.get("company_name") or "").strip(),
                    "exchange": (r.get("exchange") or "").strip(),
                    "segment": (r.get("segment") or "").strip(),
                    "is_mvp": (r.get("is_mvp") or "").strip().lower() == "true",
                    "notes": (r.get("notes") or "").strip(),
                }
            )
    return rows


def scan_report_inventory(output_dir: Path, universe: list[dict]) -> list[ReportInventoryItem]:
    items: list[ReportInventoryItem] = []
    for row in universe:
        ticker = str(row["ticker"]).upper()
        resolved = _resolve_report_files(ticker, output_dir)
        report_path = resolved["report"]
        stat = report_path.stat() if report_path else None
        size = stat.st_size if stat else None
        updated = (
            datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
            if stat
            else None
        )
        items.append(
            ReportInventoryItem(
                ticker=ticker,
                company_name=str(row.get("company_name", "")),
                exchange=str(row.get("exchange", "")),
                segment=str(row.get("segment", "")),
                is_mvp=bool(row.get("is_mvp", False)),
                has_report=report_path is not None,
                has_explanation=resolved["explanation"] is not None,
                preview_pages=list(resolved["preview_pages"]),
                report_size=size,
                updated_at=updated,
            )
        )
    return items
