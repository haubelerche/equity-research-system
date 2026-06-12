"""Data Warehouse v2 â€” Python Data Access Layer.

All production code must access v2 data through these repository modules.
Raw SQL scattered across business logic is forbidden.

Module structure:
    v2.connection     â€” shared connection factory
    v2.source_dal     â€” ingest.source_documents writes/reads
    v2.observation_dal â€” ingest.observations writes/reads
    v2.fact_dal       â€” fact.canonical_facts reads (production_facts view)
    v2.fact_promotion â€” canonical fact promotion logic
    v2.snapshot_dal   â€” research.snapshots + snapshot_items
    v2.valuation_dal  â€” valuation.runs + assumptions
    v2.report_dal     â€” report.reports + claims + citations
    v2.audit_dal      â€” audit.events (append-only)
"""
from __future__ import annotations

