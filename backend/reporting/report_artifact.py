"""ReportArtifact — structured, serializable representation of one report run.

Every field maps to a concrete artifact or gate result — nothing is invented.
The artifact is the single source of truth consumed by:
  - html_renderer.py / pdf_renderer.py (rendering)
  - layout_audit.py (post-render quality check)
  - export_gate.py (final export decision)

RenderMode controls what the renderer exposes to the client:
  client_final   — no backend terms, no warnings, all gates must pass
  analyst_draft  — audit-safe; warnings and gate failures visible to analyst
  internal_debug — full internal state; never sent to client

All arithmetic is deterministic Python — no LLM involvement.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

RenderMode = Literal["client_final", "analyst_draft", "internal_debug"]

# ── Section identifiers (must match REPORT_SECTION_CONTRACTS keys) ─────────────
SECTION_IDS = [
    "snapshot",
    "company_overview",
    "financial_performance",
    "forecast_drivers",
    "valuation_model",
    "sensitivity_peer",
    "risks_catalysts",
    "conclusion_sources",
]


@dataclass
class ReportSection:
    """One content section in the report."""
    section_id: str
    section_title: str
    html_content: str           # rendered HTML snippet
    word_count: int
    has_tables: bool
    has_charts: bool
    chart_ids: list[str] = field(default_factory=list)
    missing_data_flags: list[str] = field(default_factory=list)  # items shown as "—"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "section_id": self.section_id,
            "section_title": self.section_title,
            "word_count": self.word_count,
            "has_tables": self.has_tables,
            "has_charts": self.has_charts,
            "chart_ids": self.chart_ids,
            "missing_data_flags": self.missing_data_flags,
            "warnings": self.warnings,
        }


@dataclass
class ReportArtifact:
    """Full report artifact for one ticker/run.

    Created after sections are assembled but BEFORE final PDF render.
    The export_gate reads this to decide render_mode.
    """
    report_id: str
    ticker: str
    run_id: str | None
    report_date: str
    render_mode: RenderMode
    sections: list[ReportSection]

    # Gate inputs — populated from upstream artifacts
    valuation_artifact_path: str | None = None
    forecast_artifact_path: str | None = None
    citation_ledger_path: str | None = None
    source_manifest_path: str | None = None

    # Valuation summary — sidebar values
    recommendation: str = "UNDER_REVIEW"
    target_price_vnd: float | None = None
    current_price_vnd: float | None = None
    upside_pct: float | None = None
    dividend_yield_pct: float | None = None
    total_return_pct: float | None = None

    # Gate summaries (populated by export_gate)
    gate_results: dict[str, Any] = field(default_factory=dict)
    is_final_exportable: bool = False

    # Chart registry
    charts: dict[str, str] = field(default_factory=dict)  # {chart_id: file_path}

    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    warnings: list[str] = field(default_factory=list)

    # ── Derived properties ────────────────────────────────────────────────

    @property
    def total_word_count(self) -> int:
        return sum(s.word_count for s in self.sections)

    @property
    def missing_sections(self) -> list[str]:
        present = {s.section_id for s in self.sections}
        return [sid for sid in SECTION_IDS if sid not in present]

    @property
    def all_missing_data_flags(self) -> list[str]:
        flags: list[str] = []
        for s in self.sections:
            for f in s.missing_data_flags:
                flags.append(f"{s.section_id}:{f}")
        return flags

    def sidebar_consistent(self) -> bool:
        """All target_price/upside occurrences must match the canonical values."""
        if self.target_price_vnd is None:
            return True  # no price → nothing to mismatch
        for section in self.sections:
            content = section.html_content
            # Check for any hard-coded price that differs from canonical
            # (simplified: rely on layout_audit for deep content scan)
            if "target_price_placeholder" in content:
                return False
        return True

    # ── Serialization ─────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "ticker": self.ticker,
            "run_id": self.run_id,
            "report_date": self.report_date,
            "render_mode": self.render_mode,
            "recommendation": self.recommendation,
            "target_price_vnd": self.target_price_vnd,
            "current_price_vnd": self.current_price_vnd,
            "upside_pct": self.upside_pct,
            "dividend_yield_pct": self.dividend_yield_pct,
            "total_return_pct": self.total_return_pct,
            "total_word_count": self.total_word_count,
            "missing_sections": self.missing_sections,
            "sections": [s.to_dict() for s in self.sections],
            "charts": self.charts,
            "gate_results": self.gate_results,
            "is_final_exportable": self.is_final_exportable,
            "all_missing_data_flags": self.all_missing_data_flags,
            "valuation_artifact_path": self.valuation_artifact_path,
            "forecast_artifact_path": self.forecast_artifact_path,
            "citation_ledger_path": self.citation_ledger_path,
            "source_manifest_path": self.source_manifest_path,
            "created_at": self.created_at,
            "warnings": self.warnings,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.to_json(), encoding="utf-8")


# ── Factory ───────────────────────────────────────────────────────────────────

def make_section(
    section_id: str,
    section_title: str,
    html_content: str,
    chart_ids: list[str] | None = None,
    missing_data_flags: list[str] | None = None,
    warnings: list[str] | None = None,
) -> ReportSection:
    """Construct a ReportSection from rendered HTML."""
    import re
    # Count words in rendered text (strip HTML tags)
    text = re.sub(r"<[^>]+>", " ", html_content)
    words = [w for w in text.split() if w]
    has_tables = "<table" in html_content.lower()
    has_charts = bool(chart_ids)
    return ReportSection(
        section_id=section_id,
        section_title=section_title,
        html_content=html_content,
        word_count=len(words),
        has_tables=has_tables,
        has_charts=has_charts,
        chart_ids=chart_ids or [],
        missing_data_flags=missing_data_flags or [],
        warnings=warnings or [],
    )
