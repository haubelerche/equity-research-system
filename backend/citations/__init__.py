"""Citation grounding package — Phase 4 of the Data Trust Layer.

Modules:
  citation_map  — build structured CitationMap from FactTable + context events
  event_linker  — link catalyst events to fiscal periods with causality levels
  validator     — four deterministic citation validators (coverage, tier, numeric, causality)
"""
from backend.citations.citation_map import (
    CitationRecord,
    CitationMap,
    build_citation_map,
)
from backend.citations.event_linker import (
    CatalystEventEntry,
    link_events_to_periods,
)
from backend.citations.validator import (
    validate_citation_coverage,
    validate_source_tier,
    validate_numeric_consistency,
    validate_causality_language,
)

__all__ = [
    "CitationRecord",
    "CitationMap",
    "build_citation_map",
    "CatalystEventEntry",
    "link_events_to_periods",
    "validate_citation_coverage",
    "validate_source_tier",
    "validate_numeric_consistency",
    "validate_causality_language",
]
