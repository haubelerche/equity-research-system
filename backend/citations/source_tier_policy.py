"""Source-tier policy and export gates — Source-Provenance Rebuild, Phase 2.

Prevents aggregated API/provider sources from passing as FINAL report citations.

Tier numbering (repo convention, 0–3; LLM/None == plan's "Tier 4 unknown"):

  Tier 0 = Official source (audited BCTC, annual report, exchange disclosure, regulatory)
  Tier 1 = Trusted contextual / company IR / manually verified
  Tier 2 = Reputable media, broker reports, industry research
  Tier 3 = Aggregated API/provider (vnstock, VCI, KBS, TCBS)
  None   = Unknown or LLM-generated source  (plan "Tier 4") — ALWAYS blocked

Hard rules (plan Phase 2):
  1. Tier 3 may be used for draft generation and cross-checking.
  2. Tier 3 cannot be the only source for a FINAL quantitative claim.
  3. Unknown/None tier (Tier 4) is always blocked (draft approval AND final).
  4. Final export fails if any material quantitative claim lacks official verification.
  5. Catalyst/event claims may use Tier 0–2 but must have concrete document evidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from backend.citations.citation_map import (
    FORBIDDEN_GENERIC_LABELS,
    CitationMap,
    CitationRecord,
)
from backend.citations.validator import _load_material_metrics

# Provider tokens that must never stand alone as a final citation.
TIER3_PROVIDER_TOKENS: frozenset[str] = frozenset({
    "vnstock", "vci", "kbs", "tcbs",
})

# Bad source-label substrings (case-insensitive) that always fail.
BAD_LABEL_SUBSTRINGS: tuple[str, ...] = (
    "(vci)", "(kbs)", "(tcbs)", "(vnstock", "vnstock api",
    "balance sheet (vci)", "income statement (vci)", "cash flow (vci)",
    "nguồn không xác định", "generated citation",
)


@dataclass
class SourceTierGateResult:
    mode: str                      # "draft" | "final"
    status: str                    # "pass" | "warn" | "fail"
    export_decision: str           # "PASS" | "PASS_WITH_WARNINGS" | "BLOCKED"
    tier_counts: dict              # {0:..,1:..,2:..,3:..,"unknown":..}
    blocking_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checked: int = 0

    @property
    def passed(self) -> bool:
        return self.export_decision != "BLOCKED"

    def to_dict(self) -> dict:
        return {
            "gate": "source_tier_export",
            "mode": self.mode,
            "status": self.status,
            "export_decision": self.export_decision,
            "pass": self.passed,
            "checked": self.checked,
            "tier_counts": self.tier_counts,
            "blocking_count": len(self.blocking_reasons),
            "warning_count": len(self.warnings),
            "blocking_reasons": self.blocking_reasons[:25],
            "warnings": self.warnings[:25],
        }


def _label_is_bad(rec: CitationRecord) -> bool:
    title = (rec.source_title or "").strip().lower()
    if not title:
        return False
    if title in FORBIDDEN_GENERIC_LABELS:
        return True
    return any(sub in title for sub in BAD_LABEL_SUBSTRINGS)


def evaluate_source_tier_gate(
    citation_map: CitationMap,
    mode: str = "final",
    material_metrics: set[str] | None = None,
) -> SourceTierGateResult:
    """Evaluate the source-tier export gate for a citation map.

    Args:
        citation_map: CitationMap (key → CitationRecord).
        mode: "draft" or "final". Draft warns on Tier 3; final blocks.
        material_metrics: metrics treated as material (default: config/material_metrics.yml).
    """
    if mode not in ("draft", "final"):
        raise ValueError(f"mode must be 'draft' or 'final', got {mode!r}")
    if material_metrics is None:
        material_metrics = _load_material_metrics()

    tier_counts: dict = {0: 0, 1: 0, 2: 0, 3: 0, "unknown": 0}
    blocking: list[str] = []
    warnings: list[str] = []
    checked = 0

    for key, rec in citation_map.items():
        # Derived metrics (gross_margin, FCF...) are computed from underlying cited facts;
        # they are not directly sourced, so the gate traces through them.
        if rec.is_derived:
            continue
        checked += 1
        tier = rec.source_tier
        is_material = rec.metric in material_metrics
        has_official = rec.official_document_id is not None

        # Rule 3: unknown/None tier → always blocked. Bad/generic label → blocks in final mode, warns in draft mode.
        if tier is None:
            tier_counts["unknown"] += 1
            blocking.append(f"{key}: unknown/ungrounded source tier (Tier 4) — always blocked")
            continue
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        label_bad = _label_is_bad(rec)
        if label_bad:
            if mode == "final":
                # Final export: a provider/generic label is never acceptable as a citation.
                blocking.append(
                    f"{key}: provider/generic source label '{rec.source_title}' — blocked for final export"
                )
                continue
            else:
                # Draft mode: provider labels are allowed with a warning (Tier-3 label
                # produced from a known URI is legitimate in draft; must be improved before final).
                warnings.append(
                    f"{key}: provider/generic source label '{rec.source_title}' — allowed in draft, "
                    "must be replaced with an official document citation before final export"
                )
                continue

        if mode == "final":
            # Rule 2 + 4: final quantitative claim cannot rely on Tier 3 alone, and
            # material claims require an official verification source.
            if tier >= 3 and not has_official:
                blocking.append(
                    f"{key}: final quantitative claim cites only Tier-3 API/provider source "
                    "— requires official verification (official_document_id)"
                )
            elif is_material and not has_official:
                blocking.append(
                    f"{key}: material final claim has Tier-{tier} source but no official "
                    "document linkage — requires official verification"
                )
        else:  # draft
            if tier >= 3:
                warnings.append(
                    f"{key}: Tier-3 API/provider source — unverified by official source "
                    "(allowed in draft, must be verified before final export)"
                )

    if blocking:
        status, decision = "fail", "BLOCKED"
    elif warnings:
        status, decision = "warn", "PASS_WITH_WARNINGS"
    else:
        status, decision = "pass", "PASS"

    return SourceTierGateResult(
        mode=mode,
        status=status,
        export_decision=decision,
        tier_counts=tier_counts,
        blocking_reasons=blocking,
        warnings=warnings,
        checked=checked,
    )
