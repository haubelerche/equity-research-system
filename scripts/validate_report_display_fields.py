"""Validate that rendered report PDFs show the required valuation snapshot fields.

This is an operator-facing post-render gate. It does not recompute valuation; it
checks the actual PDF text layer so a report with headline dashes fails visibly.

Usage:
    python scripts/validate_report_display_fields.py --tickers DHG JVC
    python scripts/validate_report_display_fields.py --tickers DHG,JVC --output-dir output
"""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.reporting.pdf_quality_gate import _extract_pdf_text_best_effort


NUMBER_RE = re.compile(r"\d[\d,.]*")
PERCENT_RE = re.compile(r"[+-]?\d+(?:[,.]\d+)?\s*%")
RANGE_RE = re.compile(r"\d[\d,.]*\s*/\s*\d[\d,.]*")
TARGET_TO_MARKET_MIN = 0.95
TARGET_TO_MARKET_MAX = 1.10
TARGET_TO_MARKET_TOLERANCE = 0.001

REQUIRED_FIELDS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("gia muc tieu", NUMBER_RE),
    ("gia hien tai", NUMBER_RE),
    ("ty le tang/giam", PERCENT_RE),
    ("tong ty suat loi nhuan", PERCENT_RE),
    ("gia dong cua", NUMBER_RE),
    ("gia cao/thap 52 tuan", RANGE_RE),
    ("von hoa", NUMBER_RE),
    ("so luong co phieu", NUMBER_RE),
    ("klgd binh quan 30 phien", NUMBER_RE),
)

INVALID_TOKENS = ("—", " n/a", " - ", " chua ", " khong ")


@dataclass(frozen=True)
class ReportFieldValidation:
    ticker: str
    path: Path
    passed: bool
    missing_fields: tuple[str, ...]
    reasonableness_failures: tuple[str, ...] = ()


def _normalize(text: str) -> str:
    text = text.replace("Đ", "D").replace("đ", "d")
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", stripped.lower()).strip()


def _field_has_value(normalized_text: str, label: str, value_re: re.Pattern[str]) -> bool:
    match = re.search(re.escape(label), normalized_text)
    if match is None:
        return False
    window = normalized_text[match.end(): match.end() + 140]
    first_value = value_re.search(window)
    first_invalid = min(
        (idx for token in INVALID_TOKENS if (idx := window.find(token)) >= 0),
        default=None,
    )
    return bool(first_value and (first_invalid is None or first_value.start() < first_invalid))


def _parse_report_number(raw: str) -> float | None:
    cleaned = re.sub(r"[^\d,.\-]", "", raw)
    if not cleaned:
        return None
    try:
        return float(cleaned.replace(",", "").replace(".", ""))
    except ValueError:
        return None


def _field_number(normalized_text: str, label: str) -> float | None:
    match = re.search(re.escape(label), normalized_text)
    if match is None:
        return None
    window = normalized_text[match.end(): match.end() + 140]
    first_value = NUMBER_RE.search(window)
    first_invalid = min(
        (idx for token in INVALID_TOKENS if (idx := window.find(token)) >= 0),
        default=None,
    )
    if first_value is None or (first_invalid is not None and first_invalid < first_value.start()):
        return None
    return _parse_report_number(first_value.group(0))


def _headline_target_reasonableness_failures(normalized_text: str) -> tuple[str, ...]:
    target = _field_number(normalized_text, "gia muc tieu")
    current = _field_number(normalized_text, "gia hien tai")
    if target is None or current is None or current <= 0:
        return ()
    ratio = target / current
    if ratio < TARGET_TO_MARKET_MIN - TARGET_TO_MARKET_TOLERANCE:
        return ("headline_target_below_market_band",)
    if ratio > TARGET_TO_MARKET_MAX + TARGET_TO_MARKET_TOLERANCE:
        return ("headline_target_above_market_band",)
    return ()


def validate_pdf(path: Path, ticker: str) -> ReportFieldValidation:
    if not path.is_file():
        return ReportFieldValidation(ticker=ticker, path=path, passed=False, missing_fields=("pdf_missing",))
    text = _normalize(_extract_pdf_text_best_effort(path))
    missing = tuple(
        label for label, value_re in REQUIRED_FIELDS
        if not _field_has_value(text, label, value_re)
    )
    reasonableness = _headline_target_reasonableness_failures(text)
    return ReportFieldValidation(
        ticker=ticker,
        path=path,
        passed=not missing and not reasonableness,
        missing_fields=missing,
        reasonableness_failures=reasonableness,
    )


def _parse_tickers(raw: list[str]) -> list[str]:
    return [t.strip().upper() for item in raw for t in item.split(",") if t.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", nargs="+", required=True, help="Tickers separated by spaces or commas.")
    parser.add_argument("--output-dir", default="output", help="Directory containing <TICKER>_report.pdf.")
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir

    failed: list[ReportFieldValidation] = []
    for ticker in _parse_tickers(args.tickers):
        result = validate_pdf(output_dir / f"{ticker}_report.pdf", ticker)
        if result.passed:
            print(f"[display-fields] PASS {ticker}: {result.path}")
        else:
            failed.append(result)
            print(
                f"[display-fields] FAIL {ticker}: missing={','.join(result.missing_fields)} "
                f"reasonableness={','.join(result.reasonableness_failures)} "
                f"path={result.path}",
                file=sys.stderr,
            )

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
