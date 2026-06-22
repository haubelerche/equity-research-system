"""Pure helpers that improve retrieval quality on top of RetrievalService.retrieve()."""
from __future__ import annotations

from typing import Any, Callable

# Bilingual financial synonym map (VI canonical -> extra surface forms appended to the query).
_SYNONYMS: dict[str, list[str]] = {
    "doanh thu": ["net revenue", "revenue", "doanh thu thuần"],
    "lợi nhuận gộp": ["gross profit", "biên lợi nhuận gộp"],
    "lợi nhuận sau thuế": ["net income", "net profit", "lãi ròng"],
    "tổng tài sản": ["total assets"],
    "vốn chủ sở hữu": ["equity", "shareholders equity"],
    "lưu chuyển tiền": ["operating cash flow", "OCF", "cash flow"],
    "nợ vay": ["debt", "borrowings", "interest-bearing debt"],
    "cổ tức": ["dividend", "dividend per share"],
}


def expand_query(query: str) -> list[str]:
    """Return [original, *expansion-augmented variant] for richer recall."""
    base = query.strip()
    lower = base.lower()
    extras: list[str] = []
    for key, syns in _SYNONYMS.items():
        if key in lower:
            extras.extend(syns)
    if not extras:
        return [base]
    return [base, f"{base} {' '.join(dict.fromkeys(extras))}"]
