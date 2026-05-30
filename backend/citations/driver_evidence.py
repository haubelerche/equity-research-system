"""Catalyst driver evidence rendering — Phase 5 of the Data Trust Layer.

Converts CatalystEventEntry objects (from event_linker.link_events_to_periods)
into a structured Markdown section for equity research reports.

Rendering rules enforced from the causality taxonomy:
  contextual_event            — "diễn ra trong bối cảnh"      — no causal claim
  potential_driver            — "có thể là một yếu tố hỗ trợ" — possibility only
  management_disclosed_driver — "theo công ty, biến động này đến từ" — attributed
  validated_driver            — "được hỗ trợ bởi"             — evidence-backed

The rendered section never uses causal language for contextual_event events.
Callers (generate_report.py) must not alter the wording templates.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.citations.event_linker import CatalystEventEntry, CAUSALITY_WORDING


# Human-readable labels per causality level (Vietnamese)
_LEVEL_LABELS: dict[str, str] = {
    "validated_driver": "Yếu tố được xác nhận bằng bằng chứng độc lập",
    "management_disclosed_driver": "Yếu tố được công ty xác nhận",
    "potential_driver": "Yếu tố tiềm năng (chưa xác nhận)",
    "contextual_event": "Sự kiện bối cảnh",
}

# Render order: highest confidence first
_LEVEL_ORDER: list[str] = [
    "validated_driver",
    "management_disclosed_driver",
    "potential_driver",
    "contextual_event",
]


@dataclass
class DriverEvidenceBlock:
    """Structured catalyst events for one fiscal period, ready for rendering."""
    period: str
    total_events: int
    events_by_level: dict[str, list[CatalystEventEntry]] = field(default_factory=dict)
    rendered_md: str = ""


def _render_event_bullet(event: CatalystEventEntry) -> str:
    """Render one event as a Markdown bullet using the enforced causality wording."""
    wording = CAUSALITY_WORDING.get(event.causality_level, "diễn ra trong bối cảnh")
    title = (event.title or "").strip()
    summary = ((event.summary or "").strip())[:200]
    materiality = (event.materiality_hint or "").strip()

    core = f"**{title}** — {wording}"
    if summary and summary.lower() != title.lower():
        core += f": {summary}"
    if materiality:
        core += f" _(mức độ: {materiality})_"
    return f"- {core}"


def _build_period_block(
    period: str,
    events: list[CatalystEventEntry],
    max_events: int,
) -> DriverEvidenceBlock:
    """Group events by causality level and produce a DriverEvidenceBlock."""
    by_level: dict[str, list[CatalystEventEntry]] = {}
    for ev in events[:max_events]:
        level = ev.causality_level or "contextual_event"
        by_level.setdefault(level, []).append(ev)

    lines: list[str] = [f"#### {period}\n"]
    for level in _LEVEL_ORDER:
        level_events = by_level.get(level, [])
        if not level_events:
            continue
        label = _LEVEL_LABELS.get(level, level)
        lines.append(f"**{label}:**\n")
        for ev in level_events:
            lines.append(_render_event_bullet(ev))
        lines.append("")

    return DriverEvidenceBlock(
        period=period,
        total_events=len(events),
        events_by_level=by_level,
        rendered_md="\n".join(lines),
    )


def render_catalyst_section(
    ticker: str,
    event_periods: dict[str, list[CatalystEventEntry]],
    max_events_per_period: int = 5,
) -> str:
    """Render the '## Yếu tố thúc đẩy (Business Catalysts)' section.

    Returns a Markdown string suitable for direct insertion into the report.
    If no catalyst events are present for any period, returns a placeholder
    that explains how to populate the section — never fabricates events.

    Args:
        ticker: Ticker symbol (used only for the placeholder note).
        event_periods: dict[period_str → list[CatalystEventEntry]] from
            link_events_to_periods().
        max_events_per_period: Maximum events rendered per fiscal period.

    Returns:
        Markdown string with proper heading and causality-hedged bullets.
    """
    active = {p: evs for p, evs in event_periods.items() if evs}

    if not active:
        return (
            "## Yếu tố thúc đẩy (Business Catalysts)\n\n"
            "> _Chưa có sự kiện catalyst nào được xác minh cho **"
            f"{ticker}**. Để hiển thị phần này: chạy "
            "`scripts/ingest_catalyst_sources.py` hoặc nhập sự kiện "
            "thủ công vào bảng `fact.catalyst_events`._\n"
        )

    header_lines: list[str] = [
        "## Yếu tố thúc đẩy (Business Catalysts)\n",
        "> _Sự kiện dưới đây được liên kết với kỳ tài chính tương ứng dựa trên "
        "thời điểm xảy ra (±6 tháng so với cuối năm tài chính). "
        "Mức độ nhân quả (causality level) phản ánh bằng chứng hiện có — "
        "không phải xác nhận nhân quả tuyệt đối._\n",
    ]

    # Most recent period first
    sorted_periods = sorted(active.keys(), reverse=True)
    blocks: list[str] = []
    for period in sorted_periods:
        block = _build_period_block(period, active[period], max_events_per_period)
        if block.rendered_md.strip():
            blocks.append(block.rendered_md)

    return "\n".join(header_lines) + "\n".join(blocks)


def build_catalyst_claims(
    ticker: str,
    event_periods: dict[str, list[CatalystEventEntry]],
) -> list[dict[str, Any]]:
    """Build catalyst claim dicts for Gate 6 (catalyst evidence) evaluation.

    Each dict maps to the shape expected by gate_catalyst_evidence() which
    calls validate_event() from backend.catalysts.event_extractor.

    Important: CatalystEventEntry (from fact.catalyst_events) does not carry
    a source_document_id FK to ingest.official_documents. Gate 6 will flag
    these as lacking official-document provenance — which is the intended
    signal (not a bug). When official documents are ingested and reconciled,
    the events will be promoted with source_document_id set.

    Args:
        ticker: Ticker symbol.
        event_periods: dict[period → list[CatalystEventEntry]].

    Returns:
        List of claim dicts, one per event.
    """
    claims: list[dict[str, Any]] = []
    for period, events in event_periods.items():
        for ev in events:
            claims.append({
                "event_title": ev.title,
                "event_type": ev.event_type,
                # fact.catalyst_events stores source_id (UUID), not the integer FK
                # to ingest.official_documents — Gate 6 will flag this as missing.
                "source_document_id": None,
                "event_date": ev.occurred_at,
                "published_date": None,
                "evidence_quote": ev.summary,
                "evidence_span": None,
                "ticker": ev.ticker or ticker,
                "ticker_mapping_level": "explicit" if (ev.ticker or ticker) else "sector_level",
                "causality_level": ev.causality_level,
                # Extra context for reporting (not used by validate_event):
                "period": period,
                "claim_type": "catalyst",
                "citation_key": f"{ticker}/{period}/catalyst.{ev.event_id}",
            })
    return claims
