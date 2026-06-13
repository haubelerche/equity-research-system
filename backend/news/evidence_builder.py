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

from collections.abc import Iterable

from backend.news.types import ALLOWED_DOMAINS, EvidenceItem, RawArticle
from backend.news.whitelist import is_allowed_url

LlmExtract = Callable[[str], object]

_VALID_CONFIDENCE = {"low", "medium", "high"}
_DEFAULT_LLM_TIMEOUT_SECONDS = 60
_DEFAULT_LLM_MAX_RETRIES = 2

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
    allowed_domains: Iterable[str] = ALLOWED_DOMAINS,
) -> list[EvidenceItem]:
    """Extract validated EvidenceItems from one article. Returns [] on any invalid input.

    ``allowed_domains`` defaults to the automated-discovery whitelist; manual ingest passes
    the wider citation allowlist so a human-vetted reputable-media article yields evidence.
    """
    # Defense in depth: never build evidence from a non-whitelisted source.
    if not is_allowed_url(article.source_url, allowed_domains):
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

    # A sequential universe run must not stall indefinitely on one provider request.
    # Failed/timed-out extraction already degrades safely to no evidence in build_evidence.
    client = openai.OpenAI(
        timeout=_DEFAULT_LLM_TIMEOUT_SECONDS,
        max_retries=_DEFAULT_LLM_MAX_RETRIES,
    )
    # gpt-5.x reasoning models: (1) only the default temperature is allowed, and (2)
    # max_completion_tokens is shared with reasoning tokens — too small a budget plus the
    # default reasoning effort exhausts the budget on reasoning and returns empty content.
    # reasoning_effort="minimal" + a larger budget makes extraction emit the JSON.
    response = client.chat.completions.create(
        model=model or CHEAP_MODEL,
        max_completion_tokens=6000,
        reasoning_effort="minimal",
        messages=[
            {"role": "system", "content": "You extract factual claims and return JSON only."},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
    )
    text = response.choices[0].message.content or "[]"
    try:
        return _coerce_to_list(json.loads(text))
    except json.JSONDecodeError:
        return []


def _coerce_to_list(data: object) -> list:
    """Normalize an LLM JSON payload to a list of claim objects.

    response_format=json_object yields a top-level object; the claim list is usually the
    first list-valued field (e.g. {"facts": [...]}). A bare list passes through.
    """
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for value in data.values():
            if isinstance(value, list):
                return value
    return []
