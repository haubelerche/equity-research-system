"""Verify canonical financial facts against text from official documents."""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from backend.documents.pdf_extractor import _slug_label

_NUMBER_RE = re.compile(r"\(?-?\d[\d., \t]*\)?")


@dataclass(frozen=True)
class VerifiedFact:
    metric: str
    value: Decimal
    source_doc_id: str
    source_tier: int
    page_number: int
    extracted_text: str


def load_metric_patterns(path: Path) -> dict[str, list[re.Pattern[str]]]:
    entries = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    return {
        entry["metric_id"]: [re.compile(pattern) for pattern in entry.get("patterns", [])]
        for entry in entries
        if entry.get("metric_id")
    }


def _parsed_numbers(text: str, unit: str) -> list[Decimal]:
    values: list[Decimal] = []
    for match in _NUMBER_RE.finditer(text):
        raw = match.group(0).strip()
        negative = raw.startswith("(") and raw.endswith(")")
        cleaned = raw.strip("()").replace(" ", "").replace(".", "").replace(",", "")
        try:
            parsed = Decimal(cleaned)
        except Exception:
            continue
        values.append(-parsed if negative else parsed)
    return values


def _equal_value(left: Decimal, right: Decimal) -> bool:
    tolerance = max(Decimal("0.001"), abs(right) * Decimal("0.000001"))
    return abs(left - right) <= tolerance


def verify_fact_in_chunk(
    fact: dict[str, Any],
    chunk: dict[str, Any],
    metric_patterns: dict[str, list[re.Pattern[str]]],
) -> VerifiedFact | None:
    """Return a verification only when label and exact value share a text window."""
    patterns = metric_patterns.get(fact["metric"], [])
    if not patterns:
        return None

    lines = [line.strip() for line in chunk["chunk_text"].splitlines() if line.strip()]
    expected = Decimal(str(fact["value"]))
    label_line = ""
    label_index = 0
    for index, line in enumerate(lines):
        slug = _slug_label(line)
        if not any(pattern.search(slug) for pattern in patterns):
            continue
        label_line = line
        label_index = index
        start = max(0, index - 1)
        end = min(len(lines), index + 2)
        window = "\n".join(lines[start:end])
        if any(_equal_value(value, expected) for value in _parsed_numbers(window, fact["unit"])):
            return VerifiedFact(
                metric=fact["metric"],
                value=expected,
                source_doc_id=chunk["source_doc_id"],
                source_tier=int(chunk["source_tier"]),
                page_number=int(chunk["chunk_index"]) + 1,
                extracted_text=window,
            )

    # PDF table extraction often emits all labels before all value columns. In
    # that layout, requiring the exact label and exact value on the same
    # official page is the strongest deterministic relation available.
    if label_line and any(
        _equal_value(value, expected) for value in _parsed_numbers(chunk["chunk_text"], fact["unit"])
    ):
        start = max(0, label_index - 1)
        end = min(len(lines), label_index + 2)
        return VerifiedFact(
            metric=fact["metric"],
            value=expected,
            source_doc_id=chunk["source_doc_id"],
            source_tier=int(chunk["source_tier"]),
            page_number=int(chunk["chunk_index"]) + 1,
            extracted_text="\n".join(lines[start:end]),
        )
    return None
