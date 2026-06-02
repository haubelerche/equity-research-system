"""Citation coverage and quality gate.

Checks that:
    1. Quantitative claims have citations (not missing)
    2. Citations are not vague placeholders ("API", "Hệ thống", "System", "Database")
    3. Citations include a specific source name and date where required

Vague citation patterns that are REJECTED:
    - "Nguồn: API"
    - "Nguồn: Hệ thống"
    - "Source: System"
    - "Source: Database"
    - "Nguồn: Dữ liệu thị trường" (without specific exchange/date)
    - Any citation whose source field is None or ""

All checks are pure functions — no DB access, no LLM involvement.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from backend.harness.gates import _gate_result


# ── vague source patterns ──────────────────────────────────────────────────────

# These patterns are matched against the ASCII-folded (diacritics stripped) lowercase source text
# so that both Vietnamese Unicode and romanised forms are caught.
VAGUE_SOURCE_PATTERNS: list[str] = [
    r"^api$",
    r"^he\s*thong$",               # "hệ thống"
    r"^system$",
    r"^database$",
    r"^du\s*lieu\s*thi\s*truong$", # "dữ liệu thị trường"
    r"^market\s*data$",
    r"^internal$",
    r"^noi\s*bo$",                 # "nội bộ"
    r"^unknown$",
    r"^n/a$",
    r"^none$",
]

_COMPILED_VAGUE: list[re.Pattern[str]] = [re.compile(p, re.IGNORECASE) for p in VAGUE_SOURCE_PATTERNS]


def _ascii_fold(text: str) -> str:
    """Normalise to NFD and strip combining diacritics, then lowercase."""
    nfd = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn").lower()


# ── helpers ────────────────────────────────────────────────────────────────────

def is_vague_source(source_text: str) -> bool:
    """Return True if the source text matches any vague pattern."""
    if not source_text or not source_text.strip():
        return True
    folded = _ascii_fold(source_text.strip())
    return any(pattern.search(folded) for pattern in _COMPILED_VAGUE)


def check_citation_not_vague(
    citation: dict,
) -> dict[str, Any]:
    """Return {"passed": bool, "reason": str | None} for a single citation.

    ``citation`` must have at minimum a ``"source"`` key.
    """
    source = citation.get("source") or ""
    if not source.strip():
        return {"passed": False, "reason": "source field is empty or None"}
    if is_vague_source(source):
        return {
            "passed": False,
            "reason": f"source {source!r} matches a vague/placeholder pattern",
        }
    return {"passed": True, "reason": None}


def check_citation_has_required_fields(
    citation: dict,
    required_for_quantitative: bool = True,
) -> dict[str, Any]:
    """Check citation has: source (non-empty, non-vague), year or date.
    If required_for_quantitative=True: also require page or section reference.
    """
    issues: list[str] = []
    cid = citation.get("id", "<unknown>")

    # source check
    source_result = check_citation_not_vague(citation)
    if not source_result["passed"]:
        issues.append(f"[{cid}] {source_result['reason']}")

    # date/year check
    has_date = bool(citation.get("date") or citation.get("year") or citation.get("published_date"))
    if not has_date:
        issues.append(f"[{cid}] missing date/year field")

    # page or section for quantitative claims
    if required_for_quantitative:
        has_location = bool(citation.get("page") or citation.get("section") or citation.get("chunk_id"))
        if not has_location:
            issues.append(f"[{cid}] missing page/section/chunk_id — required for quantitative citations")

    passed = len(issues) == 0
    return {"passed": passed, "issues": issues}


# ── aggregate gate ─────────────────────────────────────────────────────────────

def run_citation_coverage_gate(
    citation_map: list[dict],
    min_coverage_ratio: float = 0.80,
) -> dict[str, Any]:
    """Run citation coverage gate over a list of citation dicts.

    Each citation dict:
        {
            "id": str,
            "source": str,
            "claim_type": str ("quantitative"|"qualitative"),
            "year": str|None,
            "page": str|None,
            "is_analyst_estimate": bool,
        }

    Checks:
    1. No vague sources → FAIL if any quantitative citation has vague source
    2. All quantitative claims have citations → FAIL if coverage < min_coverage_ratio
    3. Citations have required fields (source + date) → WARN if missing

    Returns gate result dict compatible with backend/harness/gates.py format.
    """
    blocking_reasons: list[str] = []
    warn_reasons: list[str] = []

    quant_citations = [c for c in citation_map if c.get("claim_type") == "quantitative"]
    total_quant = len(quant_citations)

    # ── Check 1: No vague sources on quantitative citations ──────────────────
    vague_count = 0
    for cit in quant_citations:
        result = check_citation_not_vague(cit)
        if not result["passed"]:
            vague_count += 1
            cid = cit.get("id", "<unknown>")
            blocking_reasons.append(
                f"quantitative citation [{cid}] has vague source: {result['reason']}"
            )

    # ── Check 2: Coverage ratio ───────────────────────────────────────────────
    # A citation is "covered" if it has a non-empty, non-vague source
    covered = sum(
        1 for c in quant_citations
        if c.get("source") and not is_vague_source(c.get("source", ""))
    )
    coverage_ratio = covered / total_quant if total_quant > 0 else 1.0

    if total_quant > 0 and coverage_ratio < min_coverage_ratio:
        blocking_reasons.append(
            f"citation coverage {coverage_ratio:.1%} < minimum {min_coverage_ratio:.1%} "
            f"({covered}/{total_quant} quantitative claims have valid citations)"
        )

    # ── Check 3: Required fields (WARN level) ────────────────────────────────
    missing_fields_count = 0
    for cit in quant_citations:
        field_result = check_citation_has_required_fields(cit, required_for_quantitative=True)
        if not field_result["passed"]:
            missing_fields_count += 1
            warn_reasons.extend(field_result["issues"])

    # Build result — blocking_reasons make it fail; warn_reasons are advisory
    # Merge warn messages into summary rather than blocking_reasons so gate can still pass
    passed = len(blocking_reasons) == 0

    all_issues_for_result = list(blocking_reasons)
    # Surface warnings in the issues list with severity=warn
    warn_issue_entries = [
        {
            "issue_id": f"CITATION_COVERAGE:WARN_{i}",
            "severity": "warn",
            "message": msg,
            "blocking": False,
        }
        for i, msg in enumerate(warn_reasons)
    ]

    result = _gate_result(
        "CITATION_COVERAGE",
        passed,
        blocking_reasons=blocking_reasons if not passed else [],
        summary={
            "total_citations": len(citation_map),
            "quantitative_citations": total_quant,
            "covered": covered,
            "coverage_ratio": round(coverage_ratio, 4),
            "min_coverage_ratio": min_coverage_ratio,
            "vague_source_count": vague_count,
            "missing_fields_count": missing_fields_count,
            "warnings": warn_reasons[:25],
        },
        severity="none" if passed else "critical",
    )

    # Append non-blocking warn issues (not overwriting the blocking ones)
    result["issues"].extend(warn_issue_entries)
    return result
