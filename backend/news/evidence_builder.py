"""Evidence builder — turn article text into structured factual claims (plan §6).

The extraction itself is done by an LLM (information-extraction tool, not a reasoning agent).
The LLM call is injected (`llm_extract`) so this module is deterministic in tests; the default
implementation calls Claude and parses strict JSON. Whatever the LLM returns, the backend
re-validates every item (plan §6): non-empty claim + evidence_text, whitelisted source, and a
normalized confidence. The article is untrusted input and is only ever inserted as data.
"""
from __future__ import annotations

import json
from collections.abc import Callable

from backend.news.types import EvidenceItem, RawArticle
from backend.news.whitelist import is_allowed_url

LlmExtract = Callable[[str], object]

_VALID_CONFIDENCE = {"low", "medium", "high"}

_PROMPT_TEMPLATE = """You are an information extraction tool.

Extract factual claims from the article below.

Rules:
- Only extract facts explicitly supported by the article.
- Do not infer beyond the text.
- Each claim must have a short supporting evidence_text.
- Do not include facts without evidence.
- Return JSON only: a list of objects.

Fields:
- claim
- evidence_text
- evidence_type
- confidence (one of: low, medium, high)

Article:
{article_text}
"""


def build_extraction_prompt(article_text: str) -> str:
    """Build the extraction prompt (plan §6). The article is inserted as untrusted data."""
    return _PROMPT_TEMPLATE.format(article_text=article_text)


def _normalize_confidence(value: object) -> str:
    text = str(value or "").strip().lower()
    return text if text in _VALID_CONFIDENCE else "medium"


def build_evidence(
    article: RawArticle,
    *,
    llm_extract: LlmExtract,
    topic: str | None = None,
    ticker: str | None = None,
    company_name: str | None = None,
) -> list[EvidenceItem]:
    """Extract validated EvidenceItems from one article. Returns [] on any invalid input."""
    # Defense in depth: never build evidence from a non-whitelisted source.
    if not is_allowed_url(article.source_url):
        return []

    prompt = build_extraction_prompt(article.raw_text)
    try:
        raw = llm_extract(prompt)
    except Exception:  # noqa: BLE001 — an extraction failure yields no evidence, never a crash
        return []
    if not isinstance(raw, list):
        return []

    items: list[EvidenceItem] = []
    for fact in raw:
        if not isinstance(fact, dict):
            continue
        claim = str(fact.get("claim") or "").strip()
        evidence_text = str(fact.get("evidence_text") or "").strip()
        if not claim or not evidence_text:
            continue
        items.append(
            EvidenceItem(
                claim=claim,
                evidence_text=evidence_text,
                evidence_type=(str(fact.get("evidence_type")).strip() or None)
                if fact.get("evidence_type")
                else None,
                confidence=_normalize_confidence(fact.get("confidence")),
                source_name=article.source_name,
                source_domain=article.source_domain,
                source_url=article.source_url,
                topic=topic,
                ticker=ticker,
                company_name=company_name,
                published_at=article.published_at,
                accessed_at=article.accessed_at,
            )
        )
    return items


def default_llm_extract(prompt: str, *, model: str | None = None) -> object:
    """Production extractor: call OpenAI and parse a strict-JSON list. Not used in tests."""
    import openai

    from backend.harness.model_adapter import CHEAP_MODEL

    client = openai.OpenAI()
    response = client.chat.completions.create(
        model=model or CHEAP_MODEL,
        max_completion_tokens=2048,
        temperature=0.0,
        messages=[
            {"role": "system", "content": "You extract factual claims and return JSON only."},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
    )
    text = response.choices[0].message.content or "[]"
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return []
