from __future__ import annotations

import csv as _csv
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, TypedDict

from backend.storage.layout import EXPORTS_BUCKET

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


@dataclass(frozen=True)
class _ExportReportState:
    has_report: bool = False
    has_explanation: bool = False
    updated_at: str | None = None
    report_size: int | None = None


class _StorageLike(Protocol):
    def list_objects(
        self,
        bucket: str,
        prefix: str = "",
        limit: int = 1000,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        ...


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _latest_timestamp(*values: object) -> str | None:
    latest: datetime | None = None
    for value in values:
        parsed = _parse_timestamp(value)
        if parsed is None:
            continue
        if latest is None or parsed > latest:
            latest = parsed
    return latest.isoformat() if latest else None


def _coerce_size(value: object) -> int | None:
    try:
        size = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return size if size >= 0 else None


def _object_name(entry: dict[str, Any], prefix: str) -> str:
    raw_name = str(entry.get("name") or entry.get("path") or entry.get("key") or "")
    if raw_name.startswith("client_reports/"):
        return raw_name
    if prefix and raw_name:
        return f"{prefix}{raw_name.lstrip('/')}"
    return raw_name


def _merge_export_object(
    states: dict[str, dict[str, object]],
    entry: dict[str, Any],
    *,
    prefix: str,
) -> None:
    name = _object_name(entry, prefix)
    parts = [part for part in name.split("/") if part]
    if len(parts) != 3 or parts[0] != "client_reports":
        return
    _, ticker, filename = parts
    if filename not in {"report.pdf", "explanation.pdf"}:
        return

    state = states.setdefault(ticker.upper(), {})
    metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
    if filename == "report.pdf":
        state["has_report"] = True
        state["report_size"] = _coerce_size(
            entry.get("size")
            or metadata.get("size")
            or metadata.get("contentLength")
        )
    else:
        state["has_explanation"] = True
    state["updated_at"] = _latest_timestamp(
        state.get("updated_at"),
        entry.get("updated_at"),
        entry.get("created_at"),
        entry.get("last_accessed_at"),
    )


def _scan_export_storage(
    storage: _StorageLike | None,
    tickers: list[str],
) -> dict[str, _ExportReportState]:
    if storage is None:
        return {}

    states: dict[str, dict[str, object]] = {}
    try:
        for entry in storage.list_objects(EXPORTS_BUCKET, prefix="client_reports/"):
            _merge_export_object(states, entry, prefix="client_reports/")
    except Exception:
        return {}

    missing = [ticker for ticker in tickers if ticker not in states]
    for ticker in missing:
        prefix = f"client_reports/{ticker}/"
        try:
            entries = storage.list_objects(EXPORTS_BUCKET, prefix=prefix)
        except Exception:
            continue
        for entry in entries:
            _merge_export_object(states, entry, prefix=prefix)

    return {
        ticker: _ExportReportState(
            has_report=bool(state.get("has_report", False)),
            has_explanation=bool(state.get("has_explanation", False)),
            updated_at=state.get("updated_at") if isinstance(state.get("updated_at"), str) else None,
            report_size=state.get("report_size") if isinstance(state.get("report_size"), int) else None,
        )
        for ticker, state in states.items()
    }


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


def scan_report_inventory(
    output_dir: Path,
    universe: list[dict],
    *,
    storage: _StorageLike | None = None,
) -> list[ReportInventoryItem]:
    tickers = [str(row["ticker"]).upper() for row in universe]
    export_states = _scan_export_storage(storage, tickers)
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
        export_state = export_states.get(ticker)
        has_report = report_path is not None or bool(export_state and export_state.has_report)
        has_explanation = resolved["explanation"] is not None or bool(export_state and export_state.has_explanation)
        report_size = size if size is not None else (export_state.report_size if export_state else None)
        updated_at = _latest_timestamp(updated, export_state.updated_at if export_state else None)
        items.append(
            ReportInventoryItem(
                ticker=ticker,
                company_name=str(row.get("company_name", "")),
                exchange=str(row.get("exchange", "")),
                segment=str(row.get("segment", "")),
                is_mvp=bool(row.get("is_mvp", False)),
                has_report=has_report,
                has_explanation=has_explanation,
                preview_pages=list(resolved["preview_pages"]),
                report_size=report_size,
                updated_at=updated_at,
            )
        )
    return items
