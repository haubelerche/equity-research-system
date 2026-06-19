from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

MIN_CLIENT_PDF_BYTES = 10_000

_FORBIDDEN_RAW_TEXT_MARKERS = (
    "benchmark_valuation_v1",
    "analyst draft",
)

_FORBIDDEN_EXTRACTED_TEXT_MARKERS = (
    *_FORBIDDEN_RAW_TEXT_MARKERS,
    "\u25a0",
    "vÃ",
    "khuyáº",
    "Ä‘",
)

_FORBIDDEN_TEXT_MARKERS = _FORBIDDEN_EXTRACTED_TEXT_MARKERS
_FORBIDDEN_BYTE_MARKERS = tuple(marker.encode("utf-8") for marker in _FORBIDDEN_RAW_TEXT_MARKERS)


@dataclass(frozen=True)
class PdfQualityResult:
    path: Path
    passed: bool
    reasons: tuple[str, ...] = ()


class PdfQualityError(RuntimeError):
    """Raised when a user-facing PDF fails deterministic safety checks."""


def _extract_pdf_text_best_effort(path: Path) -> str:
    text = ""
    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(str(path))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        text = ""
    if text.strip():
        return text

    try:
        import pdfplumber  # type: ignore

        with pdfplumber.open(str(path)) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    except Exception:
        return text


def validate_client_pdf(path: Path | str, *, min_size: int = MIN_CLIENT_PDF_BYTES) -> PdfQualityResult:
    pdf_path = Path(path)
    reasons: list[str] = []
    if not pdf_path.is_file():
        return PdfQualityResult(pdf_path, False, ("missing_file",))

    try:
        data = pdf_path.read_bytes()
    except OSError:
        return PdfQualityResult(pdf_path, False, ("unreadable_file",))

    if not data.startswith(b"%PDF"):
        reasons.append("not_pdf")
    if len(data) < min_size:
        reasons.append(f"pdf_too_small:{len(data)}<{min_size}")

    extracted = _extract_pdf_text_best_effort(pdf_path)
    for marker in _FORBIDDEN_TEXT_MARKERS:
        if marker in extracted:
            reasons.append(f"forbidden_text_marker:{marker}")

    for marker in _FORBIDDEN_BYTE_MARKERS:
        if marker in data:
            reasons.append(f"forbidden_byte_marker:{marker.decode('utf-8', errors='replace')}")

    return PdfQualityResult(pdf_path, not reasons, tuple(dict.fromkeys(reasons)))


def is_client_pdf_safe(path: Path | str) -> bool:
    return validate_client_pdf(path).passed


def require_client_pdf_safe(path: Path | str) -> Path:
    result = validate_client_pdf(path)
    if not result.passed:
        raise PdfQualityError(
            f"PDF quality gate failed for {result.path}: {', '.join(result.reasons)}"
        )
    return result.path
