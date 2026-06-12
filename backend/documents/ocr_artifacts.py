"""
OCR artifact persistence layer.

Saves raw OCR outputs (page text, candidate rows, diagnostics, metadata)
to the filesystem BEFORE any fact mapping.  This module must never write
to financial_facts — it is purely a raw-output store.

Artifact layout on disk::

    temporary_workdir/{ticker}/{fiscal_year}/{document_id}/
        metadata.json          — OCR run metadata
        pages/
            page_001.txt       — raw OCR text per page
            page_002.txt
            ...
        candidate_rows.csv     — raw parsed rows (label, value) before mapping
        diagnostics.json       — page-level diagnostics
"""

from __future__ import annotations

import csv
import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class OcrRunMetadata:
    ocr_run_id: str
    document_id: str
    ticker: str
    fiscal_year: int
    source_uri: str
    source_checksum: str
    pdf_type: str              # "scanned" | "text_based" | "unknown"
    ocr_engine: str            # e.g. "tesseract"
    ocr_lang: str              # e.g. "vie+eng"
    dpi: int
    parser_version: str        # e.g. "1.0.0"
    started_at: str            # ISO8601
    completed_at: str          # ISO8601 or ""
    status: str                # "running" | "completed" | "failed"
    pages_processed: int
    pages_failed: int
    candidate_row_count: int
    mapped_fact_count: int
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


@dataclass
class OcrPageDiagnostics:
    page_number: int
    text_path: str             # relative path to page_NNN.txt
    image_dpi: int
    ocr_lang: str
    char_count: int
    numeric_token_count: int
    financial_label_hits: int
    status: str                # "ok" | "low_text" | "failed"
    warnings: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_METADATA_FILENAME = "metadata.json"
_CANDIDATE_ROWS_FILENAME = "candidate_rows.csv"
_DIAGNOSTICS_FILENAME = "diagnostics.json"
_PAGES_DIR = "pages"
_CANDIDATE_ROW_FIELDNAMES = ["page_number", "raw_label", "raw_value"]
_OCR_ENGINE = "tesseract"
_PARSER_VERSION = "1.0.0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _page_filename(page_number: int) -> str:
    return f"page_{page_number:03d}.txt"


def _write_metadata(run_dir: Path, metadata: OcrRunMetadata) -> None:
    """Atomically write metadata.json via a temp-then-rename approach."""
    target = run_dir / _METADATA_FILENAME
    tmp = run_dir / (_METADATA_FILENAME + ".tmp")
    tmp.write_text(json.dumps(asdict(metadata), indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(target)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_file_checksum(file_path: Path) -> str:
    """Compute SHA-256 checksum of a file, return hex string."""
    h = hashlib.sha256()
    with open(file_path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def init_ocr_run(
    ticker: str,
    fiscal_year: int,
    document_id: str,
    source_uri: str,
    source_checksum: str,
    pdf_type: str,
    ocr_lang: str,
    dpi: int,
    base_dir: Path | None = None,
) -> tuple[OcrRunMetadata, Path]:
    """Initialize an OCR run directory and write initial metadata.json.

    Returns (metadata, run_dir).
    """
    if base_dir is None:
        raise ValueError("base_dir must be an explicit temporary OCR working directory")
    run_dir = base_dir / ticker / str(fiscal_year) / document_id
    (run_dir / _PAGES_DIR).mkdir(parents=True, exist_ok=True)

    metadata = OcrRunMetadata(
        ocr_run_id=uuid.uuid4().hex,
        document_id=document_id,
        ticker=ticker,
        fiscal_year=fiscal_year,
        source_uri=source_uri,
        source_checksum=source_checksum,
        pdf_type=pdf_type,
        ocr_engine=_OCR_ENGINE,
        ocr_lang=ocr_lang,
        dpi=dpi,
        parser_version=_PARSER_VERSION,
        started_at=_now_iso(),
        completed_at="",
        status="running",
        pages_processed=0,
        pages_failed=0,
        candidate_row_count=0,
        mapped_fact_count=0,
        warnings=[],
        errors=[],
    )
    _write_metadata(run_dir, metadata)
    return metadata, run_dir


def save_page_text(run_dir: Path, page_number: int, text: str) -> Path:
    """Save raw OCR text for one page. Returns path written."""
    dest = run_dir / _PAGES_DIR / _page_filename(page_number)
    dest.write_text(text, encoding="utf-8")
    return dest


def save_candidate_rows(run_dir: Path, rows: list[dict]) -> Path:
    """Save candidate_rows.csv.

    rows is a list of dicts with keys: page_number, raw_label, raw_value.
    """
    dest = run_dir / _CANDIDATE_ROWS_FILENAME
    with open(dest, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_CANDIDATE_ROW_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return dest


def save_diagnostics(run_dir: Path, page_diagnostics: list[OcrPageDiagnostics]) -> Path:
    """Save diagnostics.json."""
    dest = run_dir / _DIAGNOSTICS_FILENAME
    payload = [asdict(d) for d in page_diagnostics]
    dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return dest


def finalize_ocr_run(
    run_dir: Path,
    metadata: OcrRunMetadata,
    pages_processed: int,
    pages_failed: int,
    candidate_row_count: int,
    mapped_fact_count: int,
    warnings: list[str],
    errors: list[str],
    status: str = "completed",
) -> OcrRunMetadata:
    """Update metadata with final stats and write metadata.json.

    Returns the updated OcrRunMetadata.
    """
    metadata.pages_processed = pages_processed
    metadata.pages_failed = pages_failed
    metadata.candidate_row_count = candidate_row_count
    metadata.mapped_fact_count = mapped_fact_count
    metadata.warnings = list(warnings)
    metadata.errors = list(errors)
    metadata.status = status
    metadata.completed_at = _now_iso()
    _write_metadata(run_dir, metadata)
    return metadata


def load_ocr_run_metadata(run_dir: Path) -> OcrRunMetadata:
    """Load metadata.json from a run directory."""
    data = json.loads((run_dir / _METADATA_FILENAME).read_text(encoding="utf-8"))
    return OcrRunMetadata(**data)


def load_page_text(run_dir: Path, page_number: int) -> str:
    """Load raw OCR text for a specific page."""
    return (run_dir / _PAGES_DIR / _page_filename(page_number)).read_text(encoding="utf-8")
