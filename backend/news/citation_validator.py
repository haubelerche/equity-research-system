"""Citation validator — code-based check of an Editor report (plan §8).

This is a deterministic function, not an agent. It verifies that every URL the Editor cited
(a) is on the whitelist and (b) appears in the evidence packet that was handed to the Editor,
and that a report making claims actually cites something. If validation fails the report must
not be published — it is returned for revision or flagged insufficient-evidence (plan §8).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from backend.news.types import EvidencePacket
from backend.news.whitelist import is_allowed_url

_URL_RE = re.compile(r"https?://[^\s)\]<>\"']+")
# Trailing punctuation that is almost always sentence punctuation, not part of the URL.
_TRAILING = ".,;:!?’”'\")]}"


def extract_urls(text: str) -> list[str]:
    """Extract http(s) URLs from free text, stripping trailing sentence punctuation, deduped."""
    seen: set[str] = set()
    out: list[str] = []
    for match in _URL_RE.findall(text or ""):
        url = match.rstrip(_TRAILING)
        if url and url not in seen:
            seen.add(url)
            out.append(url)
    return out


@dataclass(frozen=True)
class CitationValidationResult:
    passed: bool
    citation_count: int
    cited_urls: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)


def validate_citations(report_markdown: str, packet: EvidencePacket) -> CitationValidationResult:
    """Validate an Editor report against the evidence packet it was generated from."""
    evidence_urls = {item.source_url for item in packet.evidence}
    cited = extract_urls(report_markdown)
    issues: list[str] = []
    valid_citations = 0

    for url in cited:
        if not is_allowed_url(url):
            issues.append(f"non_whitelisted_source:{url}")
            continue
        if url not in evidence_urls:
            issues.append(f"citation_not_in_evidence:{url}")
            continue
        valid_citations += 1

    # A report that has evidence available but cites nothing is unsupported (plan §8).
    if evidence_urls and valid_citations == 0:
        issues.append("no_citations")

    return CitationValidationResult(
        passed=not issues,
        citation_count=valid_citations,
        cited_urls=cited,
        issues=issues,
    )
