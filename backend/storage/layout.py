"""Validated Supabase Storage bucket and object-key contract."""
from __future__ import annotations

import re
from urllib.parse import quote

SOURCES_BUCKET = "sources"
RUNS_BUCKET = "runs"
EXPORTS_BUCKET = "exports"
ARCHIVE_BUCKET = "archive"
REQUIRED_BUCKETS = (SOURCES_BUCKET, RUNS_BUCKET, EXPORTS_BUCKET, ARCHIVE_BUCKET)

_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9_.-]+$")
_RUN_ARTIFACT_NAMES = {
    "manifest.json",
    "facts_snapshot.json",
    "facts_report.html",
    "facts_report.pdf",
    "forecast.json",
    "valuation.json",
    "evidence_pack.json",
    "review_packet.json",
    "quality_gate.json",
    "report.md",
    "report.html",
    "report.pdf",
}
_EXPORT_NAMES = {"report.pdf", "report.html", "report.md"}


def _component(value: str, label: str) -> str:
    normalized = str(value).strip()
    if not normalized or not _SAFE_COMPONENT.fullmatch(normalized):
        raise ValueError(f"Unsafe {label}: {value!r}")
    return normalized


def source_document_key(ticker: str, year: int | str, source_doc_id: str) -> str:
    return (
        f"official_documents/{_component(ticker.upper(), 'ticker')}/"
        f"{_component(str(year), 'year')}/{_component(source_doc_id, 'source_doc_id')}.pdf"
    )


def run_artifact_key(run_id: str, artifact_name: str) -> str:
    if artifact_name not in _RUN_ARTIFACT_NAMES:
        raise ValueError(f"Unsupported production run artifact: {artifact_name!r}")
    return f"{_component(run_id, 'run_id')}/{artifact_name}"


def run_chart_key(run_id: str, chart_name: str) -> str:
    name = _component(chart_name, "chart_name")
    if name.lower().endswith(".png"):
        name = name[:-4]
    return f"{_component(run_id, 'run_id')}/charts/{name}.png"


def approved_export_key(ticker: str, run_id: str, report_name: str) -> str:
    if report_name not in _EXPORT_NAMES:
        raise ValueError(f"Unsupported approved export: {report_name!r}")
    return (
        f"approved_reports/{_component(ticker.upper(), 'ticker')}/"
        f"{_component(run_id, 'run_id')}/{report_name}"
    )


def archive_key(category: str, relative: str) -> str:
    if category not in {"legacy", "debug", "failed_runs"}:
        raise ValueError(f"Unsupported archive category: {category!r}")
    parts = relative.replace("\\", "/").split("/")
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"Unsafe archive relative path: {relative!r}")
    return f"{category}/{'/'.join(quote(part, safe='._-') for part in parts)}"


def validate_bucket_path(bucket: str, path: str) -> None:
    if bucket not in REQUIRED_BUCKETS:
        raise ValueError(f"Unsupported storage bucket: {bucket!r}")
    normalized = path.replace("\\", "/").strip("/")
    if normalized != path or not normalized or ".." in normalized.split("/"):
        raise ValueError(f"Unsafe storage path: {path!r}")
