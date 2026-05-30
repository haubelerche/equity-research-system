"""Deterministic citation validators — Phase 4 of the Data Trust Layer.

Four validators, all purely deterministic (no LLM calls):

  1. validate_citation_coverage  — every [^key] tag in report text must resolve
  2. validate_source_tier        — material claims must not rely solely on Tier 3
  3. validate_numeric_consistency — report_claims values must match canonical facts
  4. validate_causality_language  — causal language must not appear with contextual events

These validators are used by scripts/evaluate_report.py and replace the
prior evaluation logic that had silent passes and incomplete coverage.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.citations.citation_map import CitationMap, FORBIDDEN_GENERIC_LABELS
from backend.citations.event_linker import CAUSAL_PATTERNS


# ── Validation result containers ──────────────────────────────────────────────

@dataclass
class ValidationResult:
    gate: str
    status: str           # "pass" | "warn" | "fail"
    critical_fail: bool
    checked: int
    issue_count: int
    issues: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status == "pass"

    def to_dict(self) -> dict:
        return {
            "gate": self.gate,
            "status": self.status,
            "pass": self.passed,
            "critical_fail": self.critical_fail,
            "checked": self.checked,
            "issue_count": self.issue_count,
            "issues": self.issues[:20],
            **self.details,
        }


# ── Material metrics loader ────────────────────────────────────────────────────

def _load_material_metrics() -> set[str]:
    """Load material metrics from config/material_metrics.yml.

    Falls back to a hardcoded minimal set if the file is not found.
    """
    try:
        import yaml  # type: ignore[import-untyped]
        config_path = Path(__file__).resolve().parents[2] / "config" / "material_metrics.yml"
        if config_path.exists():
            data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            metrics: set[str] = set()
            for section in data.values():
                if isinstance(section, list):
                    metrics.update(section)
            return metrics
    except Exception:  # noqa: BLE001
        pass
    # Fallback minimal set
    return {
        "revenue.net", "gross_profit.total", "net_income.parent",
        "total_assets.ending", "equity.parent", "operating_cash_flow.total",
        "eps.basic", "total_debt.ending", "capex.total",
        "free_cash_flow.total", "gross_margin", "net_margin",
    }


# ── Footnote tag pattern ───────────────────────────────────────────────────────
# Matches [^revenue_net_2023] or [^revenue_net_2023FY]
_FOOTNOTE_TAG_RE = re.compile(r"\[\^([\w]+)\]")

# Citation key pattern in a footnote: metric_year → ticker/yearFY/metric.with.dots
def _tag_to_key_candidates(tag: str, ticker: str) -> list[str]:
    """Convert a footnote tag like 'revenue_net_2023' to possible CitationMap keys."""
    # Tag format: {metric_with_underscores}_{year}
    # e.g. "revenue_net_2023" → "revenue.net" + "2023FY"
    m = re.match(r"^(.+?)_(\d{4})(?:FY)?$", tag)
    if not m:
        return []
    metric_slug = m.group(1).replace("_", ".")
    year = m.group(2)
    return [f"{ticker}/{year}FY/{metric_slug}"]


# ── 1. validate_citation_coverage ─────────────────────────────────────────────

def validate_citation_coverage(
    report_text: str,
    citation_map: CitationMap,
    ticker: str = "",
) -> ValidationResult:
    """Gate: every [^key] footnote tag in report text must resolve in citation_map.

    Also checks that every key in citation_map has at least one [^key] tag in the
    report (citation map completeness — warns if not, does not fail).
    """
    tags = _FOOTNOTE_TAG_RE.findall(report_text)
    if not tags:
        return ValidationResult(
            gate="citation_coverage",
            status="warn",
            critical_fail=False,
            checked=0,
            issue_count=1,
            issues=["No footnote tags [^key] found in report — citation coverage unverifiable"],
            details={"total_tags": 0, "resolved": 0, "unresolved": []},
        )

    resolved = 0
    unresolved: list[str] = []
    for tag in set(tags):
        candidates = _tag_to_key_candidates(tag, ticker)
        found = any(k in citation_map for k in candidates) or (
            # Also try exact match with tag as key suffix
            any(k.endswith(f"/{tag.replace('_', '.')}") for k in citation_map)
        )
        if found:
            resolved += 1
        else:
            unresolved.append(tag)

    total = len(set(tags))
    ratio = resolved / total if total > 0 else 1.0
    critical = len(unresolved) > total * 0.5

    return ValidationResult(
        gate="citation_coverage",
        status="pass" if not unresolved else ("fail" if critical else "warn"),
        critical_fail=critical,
        checked=total,
        issue_count=len(unresolved),
        issues=[f"Unresolved tag [^{t}]" for t in unresolved[:10]],
        details={
            "total_tags": total,
            "resolved": resolved,
            "coverage_ratio": round(ratio, 3),
            "unresolved_tags": unresolved[:10],
        },
    )


# ── 2. validate_source_tier ────────────────────────────────────────────────────

def validate_source_tier(
    citation_map: CitationMap,
    report_status: str = "draft",
    material_metrics: set[str] | None = None,
) -> ValidationResult:
    """Gate: material quantitative claims must not rely solely on Tier 3 sources.

    Behavior:
      - draft report:    Tier 3-only material citation → WARN
      - approved/export: Tier 3-only material citation → FAIL (blocks export)

    Also fails any citation whose source_title is a FORBIDDEN_GENERIC_LABEL
    (e.g., "Báo cáo tài chính (vnstock API)").
    """
    if material_metrics is None:
        material_metrics = _load_material_metrics()

    issues: list[str] = []
    tier3_material: list[str] = []
    generic_label: list[str] = []
    checked = 0

    for key, rec in citation_map.items():
        checked += 1
        metric = rec.metric

        # Check for forbidden generic labels
        title_lower = (rec.source_title or "").strip().lower()
        if title_lower in FORBIDDEN_GENERIC_LABELS:
            generic_label.append(key)
            issues.append(f"{key}: source_title is a generic provider label ('{rec.source_title}')")

        # Check Tier 3-only on material metrics
        if metric in material_metrics and not rec.is_derived:
            tier = rec.source_tier
            if tier is None or tier >= 3:
                tier3_material.append(key)
                issues.append(
                    f"{key}: material metric '{metric}' has only Tier-{tier or '?'} source"
                    f" — needs Tier 0/1 corroboration"
                )

    critical = len(tier3_material) > 0 and report_status in ("approved", "exported")
    warn = len(tier3_material) > 0 or len(generic_label) > 0

    if critical:
        status = "fail"
    elif warn:
        status = "warn"
    else:
        status = "pass"

    return ValidationResult(
        gate="citation_source_tier",
        status=status,
        critical_fail=critical,
        checked=checked,
        issue_count=len(issues),
        issues=issues[:15],
        details={
            "tier3_only_material_citations": tier3_material[:10],
            "generic_label_citations": generic_label[:10],
            "report_status": report_status,
        },
    )


# ── 3. validate_numeric_consistency ───────────────────────────────────────────

def validate_numeric_consistency(
    report_claims: list[dict[str, Any]],
    citation_map: CitationMap,
    tolerance_pct: float = 1.0,
) -> ValidationResult:
    """Gate: values in report_claims must match canonical facts within tolerance.

    Primary input is structured report_claims objects (not Markdown regex).
    Markdown number extraction is a secondary guardrail only.

    Args:
        report_claims: List of claim dicts with keys: metric, period, value_mentioned, ticker
        citation_map: CitationMap built from the same FactTable
        tolerance_pct: Acceptable deviation in % (default 1%)
    """
    if not report_claims:
        return ValidationResult(
            gate="numeric_consistency",
            status="warn",
            critical_fail=False,
            checked=0,
            issue_count=1,
            issues=["No structured report_claims provided — numeric consistency unverifiable"],
            details={"tolerance_pct": tolerance_pct},
        )

    issues: list[str] = []
    checked = 0

    for claim in report_claims:
        if claim.get("claim_type") not in ("quantitative", "valuation"):
            continue
        ticker = claim.get("ticker", "")
        period = claim.get("period", "")
        metric = claim.get("metric", "")
        value_mentioned = claim.get("value_mentioned")
        if value_mentioned is None or not metric or not period:
            continue

        key = f"{ticker}/{period}/{metric}"
        rec = citation_map.get(key)
        if rec is None:
            issues.append(f"Claim {key}: value={value_mentioned} — no citation record found")
            checked += 1
            continue

        checked += 1
        canonical = rec.value
        if canonical == 0:
            continue
        deviation_pct = abs(value_mentioned - canonical) / abs(canonical) * 100
        if deviation_pct > tolerance_pct:
            issues.append(
                f"{key}: report={value_mentioned:,.1f}, canonical={canonical:,.1f}, "
                f"deviation={deviation_pct:.1f}% (threshold {tolerance_pct}%)"
            )

    critical = len(issues) > max(1, checked * 0.1)

    return ValidationResult(
        gate="numeric_consistency",
        status="pass" if not issues else ("fail" if critical else "warn"),
        critical_fail=critical,
        checked=checked,
        issue_count=len(issues),
        issues=issues[:10],
        details={"tolerance_pct": tolerance_pct, "claims_checked": checked},
    )


# ── 4. validate_causality_language ────────────────────────────────────────────

def validate_causality_language(
    report_text: str,
    event_periods: dict[str, list[Any]],
) -> ValidationResult:
    """Gate: causal language must not appear near contextual_event catalyst mentions.

    Scans the report text for causal keywords and flags any that appear in
    sections discussing events with causality_level = 'contextual_event'.

    This is a heuristic check — false positives are possible but the gate only
    produces WARNings, never a hard FAIL, since sentence-level attribution
    requires context.
    """
    causal_re = re.compile(
        "|".join(CAUSAL_PATTERNS),
        re.IGNORECASE,
    )

    # Collect titles of contextual_event events to look for in text
    contextual_titles: list[str] = []
    for period_events in event_periods.values():
        for event in period_events:
            cl = getattr(event, "causality_level", "contextual_event")
            if cl == "contextual_event":
                title = getattr(event, "title", "")
                if title and len(title) > 8:
                    contextual_titles.append(title[:60])

    if not contextual_titles:
        return ValidationResult(
            gate="causality_language",
            status="pass",
            critical_fail=False,
            checked=0,
            issue_count=0,
            issues=[],
            details={"contextual_events_checked": 0},
        )

    # Split report into sentences and check each
    sentences = re.split(r"[.!?\n]", report_text)
    issues: list[str] = []
    checked = len(sentences)

    for sentence in sentences:
        # Check if sentence mentions any contextual event title
        mentions_event = any(
            title[:30].lower() in sentence.lower() for title in contextual_titles
        )
        if not mentions_event:
            continue
        # Check for causal language in that sentence
        causal_matches = causal_re.findall(sentence)
        if causal_matches:
            preview = sentence.strip()[:100]
            issues.append(
                f"Causal language {causal_matches!r} in sentence mentioning contextual event: "
                f"'{preview}...'"
            )

    return ValidationResult(
        gate="causality_language",
        status="pass" if not issues else "warn",
        critical_fail=False,  # causality language is always warn, not hard fail
        checked=checked,
        issue_count=len(issues),
        issues=issues[:10],
        details={"contextual_events_checked": len(contextual_titles)},
    )
