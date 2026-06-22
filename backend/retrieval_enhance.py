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


def reciprocal_rank_fusion(
    result_lists: list[list[dict[str, Any]]], *, k: int = 60, key: str = "chunk_id"
) -> list[dict[str, Any]]:
    """Fuse multiple ranked lists by Reciprocal Rank Fusion; returns one de-duplicated list."""
    scores: dict[Any, float] = {}
    first_seen: dict[Any, dict[str, Any]] = {}
    for results in result_lists:
        for rank, item in enumerate(results, start=1):
            ident = item.get(key)
            if ident is None:
                continue
            scores[ident] = scores.get(ident, 0.0) + 1.0 / (k + rank)
            first_seen.setdefault(ident, item)
    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return [first_seen[ident] for ident, _ in ordered]


def _default_batch_scorer(query: str, texts: list[str]) -> list[float]:
    """Batch relevance scores via the production LLM in one call. Lazy import keeps tests pure."""
    from backend.harness.model_adapter import score_relevance_batch
    return score_relevance_batch(query, texts)


def llm_rerank(
    query: str, candidates: list[dict[str, Any]], *, top_k: int = 5,
    batch_scorer: Callable[[str, list[str]], list[float]] | None = None,
) -> list[dict[str, Any]]:
    """Re-order candidates by an LLM relevance score (single batched call); return the top_k."""
    if not candidates:
        return []
    score_fn = batch_scorer or _default_batch_scorer
    texts = [str(c.get("text") or "") for c in candidates]
    scores = list(score_fn(query, texts))
    scores = (scores + [0.0] * len(candidates))[:len(candidates)]
    ranked = sorted(zip(candidates, scores), key=lambda cs: cs[1], reverse=True)
    return [c for c, _ in ranked[:top_k]]
