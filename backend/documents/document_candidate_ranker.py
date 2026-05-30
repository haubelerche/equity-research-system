"""Document candidate ranking — Source-Provenance Rebuild, Phase 3A.

Ranks discovered candidates so the system picks the most authoritative document per
(fiscal_year, document_type):

    company IR > HOSE/HNX/SSC > official regulator > reputable mirror > media

Low-confidence candidates are never auto-promoted; they are flagged needs_review.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from backend.documents.connectors.base import SOURCE_PRIORITY, DocumentCandidate

DEFAULT_MIN_CONFIDENCE = 0.6


@dataclass
class RankedCandidate:
    candidate: DocumentCandidate
    selected: bool
    needs_review: bool
    reason: str


@dataclass
class RankingResult:
    selected: list[DocumentCandidate] = field(default_factory=list)
    needs_review: list[DocumentCandidate] = field(default_factory=list)
    superseded: list[DocumentCandidate] = field(default_factory=list)
    all_ranked: list[RankedCandidate] = field(default_factory=list)


def _priority(source_name: str) -> int:
    return SOURCE_PRIORITY.get(source_name, 9)


def rank_candidates(
    candidates: list[DocumentCandidate],
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
) -> RankingResult:
    """Group by (fiscal_year, document_type); select the best per group.

    Selection within a group: highest source priority, then highest confidence. The
    winner must also clear `min_confidence` to be auto-selected; otherwise it is flagged
    needs_review (not promoted).
    """
    groups: dict[tuple, list[DocumentCandidate]] = {}
    for c in candidates:
        groups.setdefault((c.fiscal_year, c.document_type), []).append(c)

    result = RankingResult()
    for (year, dtype), group in groups.items():
        group_sorted = sorted(group, key=lambda c: (_priority(c.source_name), -c.confidence))
        winner = group_sorted[0]
        losers = group_sorted[1:]

        if winner.confidence >= min_confidence:
            winner.ranking_reason = (
                f"selected: source={winner.source_name} (priority {_priority(winner.source_name)}), "
                f"confidence={winner.confidence:.2f} ≥ {min_confidence}"
            )
            result.selected.append(winner)
            result.all_ranked.append(RankedCandidate(winner, True, False, winner.ranking_reason))
        else:
            winner.ranking_reason = (
                f"needs_review: confidence={winner.confidence:.2f} < {min_confidence} "
                f"(year={year}, type={dtype})"
            )
            result.needs_review.append(winner)
            result.all_ranked.append(RankedCandidate(winner, False, True, winner.ranking_reason))

        for l in losers:
            l.ranking_reason = (
                f"superseded by {winner.source_name} for {year}/{dtype}"
            )
            result.superseded.append(l)
            result.all_ranked.append(RankedCandidate(l, False, False, l.ranking_reason))

    return result
