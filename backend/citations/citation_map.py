"""Structured CitationMap — Phase 4 of the Data Trust Layer.

Replaces the ad-hoc `_build_citation_map()` in scripts/generate_report.py with a
properly typed, source-tier-aware mapping from quantitative claims to their evidence.

CitationMap key format: "{ticker}/{period}/{metric}"
  e.g. "DHG/2023FY/revenue.net"

Each CitationRecord carries:
  - The numeric value and its display string
  - Full source provenance (source_id, source_uri, source_title, source_tier)
  - Associated catalyst event IDs for that fiscal period

Source title construction priority:
  1. source_title from FactEntry (set by connector, e.g. "Báo cáo KQKD DHG 2023FY (KBS)")
  2. source_uri parsed to a readable label
  3. Tier-based fallback label (never "vnstock API" — that is a forbidden generic label)
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from backend.facts.normalizer import FactEntry, FactTable

# Tier labels shown in report footnotes
_TIER_LABELS = {
    0: "Tier 0 — Báo cáo kiểm toán / Công bố sàn",
    1: "Tier 1 — Tài liệu IR / Dữ liệu kiểm chứng thủ công",
    2: "Tier 2 — Nguồn thị trường uy tín",
    3: "Tier 3 — API tổng hợp (cần kiểm chứng)",
}

# These labels must never appear in a report footnote — they are provider labels, not citations.
FORBIDDEN_GENERIC_LABELS: frozenset[str] = frozenset({
    "báo cáo tài chính (vnstock api)",
    "báo cáo tài chính (nguồn không xác định)",
    "dữ liệu tài chính canonical",
    "canonical financial facts",
    "nguồn không xác định",
    "bảng cân đối kế toán (vnstock api)",
    "báo cáo lưu chuyển tiền tệ (vnstock api)",
    "dữ liệu thị trường (vnstock api)",
})

_LINE_ITEM_LABELS: dict[str, str] = {
    "revenue.net": "Doanh thu thuần",
    "gross_profit.total": "Lợi nhuận gộp",
    "net_income.parent": "Lợi nhuận sau thuế (cty mẹ)",
    "eps.basic": "EPS cơ bản (VND/CP)",
    "operating_cash_flow.total": "Dòng tiền hoạt động",
    "total_assets.ending": "Tổng tài sản",
    "equity.parent": "Vốn chủ sở hữu (cty mẹ)",
    "ebitda.total": "EBITDA",
    "capex.total": "CAPEX",
    "depreciation.total": "Khấu hao",
    "total_debt.ending": "Tổng nợ vay",
    "cash_and_equivalents.ending": "Tiền & tương đương tiền",
    "gross_margin": "Biên lợi nhuận gộp",
    "net_margin": "Biên lợi nhuận ròng",
    "free_cash_flow.total": "Dòng tiền tự do",
}


def _build_source_title(entry: FactEntry) -> str:
    """Derive a human-readable, non-generic source title from a FactEntry.

    Ensures the returned title is never one of the FORBIDDEN_GENERIC_LABELS.
    """
    # 1. Use connector-supplied title if it's not forbidden
    raw = (entry.source_title or "").strip()
    if raw and raw.lower() not in FORBIDDEN_GENERIC_LABELS:
        return raw

    # 2. Build from source_uri if it looks useful
    uri = (entry.source_uri or "").strip()
    if uri.startswith("vnstock://"):
        # e.g. "vnstock://kbs/finance/income_statement/DHG?period=year"
        parts = uri.removeprefix("vnstock://").split("/")
        provider = parts[0].upper() if parts else "vnstock"
        stmt = parts[2].replace("_", " ").title() if len(parts) > 2 else "Financial Data"
        tier_label = _TIER_LABELS.get(entry.source_tier or 3, "")
        return f"{stmt} ({provider}) [{tier_label}]"
    if uri.startswith("file://"):
        return f"Tệp nội bộ đã kiểm chứng [{_TIER_LABELS.get(entry.source_tier or 1, '')}]"
    if uri:
        return f"Nguồn: {uri[:80]}"

    # 3. Tier-based fallback — honest about what we know
    tier = entry.source_tier
    if tier == 0:
        return "Báo cáo kiểm toán / Công bố sàn chứng khoán [Tier 0]"
    if tier == 1:
        return "Tài liệu IR / Dữ liệu kiểm chứng thủ công [Tier 1]"
    if tier == 2:
        return "Nguồn thị trường uy tín [Tier 2]"
    return "Dữ liệu API tổng hợp — chưa kiểm chứng độc lập [Tier 3]"


def _format_value(value: float, unit: str) -> str:
    if unit == "vnd_bn":
        return f"{value:,.1f} tỷ VND"
    if unit == "vnd":
        return f"{value:,.0f} VND/CP"
    if unit in ("ratio", "pct"):
        return f"{value:.2%}"
    return str(value)


@dataclass
class CitationRecord:
    """Full citation record for one (ticker, period, metric) triple."""
    key: str                          # "{ticker}/{period}/{metric}"
    ticker: str
    period: str
    fiscal_year: int
    metric: str
    metric_label: str
    value: float
    value_display: str
    unit: str
    fact_id: str
    source_id: str
    source_uri: str
    source_title: str                 # human-readable, never a generic label
    source_tier: int | None
    tier_label: str
    published_at: str
    reliability_tier: int | None
    context_event_ids: list[str] = field(default_factory=list)
    is_derived: bool = False
    # Verification linkage (Phase 1/6): FK to ingest.official_documents. None until a
    # canonical fact is reconciled against an official source. Final-export gate requires
    # this to be non-None for material quantitative claims.
    official_document_id: int | None = None
    reconciliation_status: str = "missing_official"

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "ticker": self.ticker,
            "period": self.period,
            "fiscal_year": self.fiscal_year,
            "metric": self.metric,
            "metric_label": self.metric_label,
            "value": self.value,
            "value_display": self.value_display,
            "unit": self.unit,
            "fact_id": self.fact_id,
            "source_id": self.source_id,
            "source_uri": self.source_uri,
            "source_title": self.source_title,
            "source_tier": self.source_tier,
            "tier_label": self.tier_label,
            "published_at": self.published_at,
            "reliability_tier": self.reliability_tier,
            "context_event_ids": self.context_event_ids,
            "is_derived": self.is_derived,
            "official_document_id": self.official_document_id,
            "reconciliation_status": self.reconciliation_status,
        }


# CitationMap: key → CitationRecord
CitationMap = dict[str, CitationRecord]


def build_citation_map(
    ticker: str,
    fact_table: FactTable,
    context_events: dict[str, list[Any]] | None = None,
) -> CitationMap:
    """Build a CitationMap from the FactTable and optional catalyst context events.

    Only non-derived entries (source_id is not None) receive full source provenance.
    Derived metrics (gross_margin, free_cash_flow, etc.) are included but flagged
    as is_derived=True with source_tier=None.

    Args:
        ticker: Ticker symbol.
        fact_table: FactTable from build_fact_table() + compute_derived().
        context_events: Optional dict from event_linker.link_events_to_periods().
            Maps period → list of CatalystEventEntry.

    Returns:
        CitationMap keyed by "{ticker}/{period}/{metric}".
    """
    cmap: CitationMap = {}

    for metric, periods in fact_table.items():
        for period, entry in periods.items():
            if not isinstance(entry, FactEntry):
                continue  # safety: skip bare floats (should not exist after Phase 2)

            # Derive fiscal year from period string e.g. "2023FY" → 2023
            try:
                fiscal_year = int(period[:4])
            except (ValueError, IndexError):
                continue

            key = f"{ticker}/{period}/{metric}"
            unit = "vnd_bn"  # default; FactEntry doesn't carry unit directly

            source_title = _build_source_title(entry)
            tier = entry.source_tier
            tier_label = _TIER_LABELS.get(tier, "") if tier is not None else "Chỉ số phái sinh"

            # Gather context event IDs for this period
            period_events = (context_events or {}).get(period, [])
            event_ids = [str(getattr(e, "event_id", "")) for e in period_events]

            cmap[key] = CitationRecord(
                key=key,
                ticker=ticker,
                period=period,
                fiscal_year=fiscal_year,
                metric=metric,
                metric_label=_LINE_ITEM_LABELS.get(metric, metric),
                value=entry.value,
                value_display=_format_value(entry.value, unit),
                unit=unit,
                fact_id=entry.fact_id or "",
                source_id=entry.source_id or "",
                source_uri=entry.source_uri or "",
                source_title=source_title,
                source_tier=tier,
                tier_label=tier_label,
                published_at="",
                reliability_tier=entry.reliability_tier,
                context_event_ids=event_ids,
                is_derived=entry.is_derived(),
            )

    return cmap


def legacy_dict_to_citation_map(legacy: dict[str, dict]) -> CitationMap:
    """Rebuild a typed CitationMap from the legacy dict form (inverse of below).

    Used by the source-tier gate and evaluator, which operate on CitationRecord objects.
    Unknown/missing fields fall back to safe defaults.
    """
    out: CitationMap = {}
    for key, rec in legacy.items():
        if isinstance(rec, CitationRecord):
            out[key] = rec
            continue
        out[key] = CitationRecord(
            key=key,
            ticker=rec.get("ticker", ""),
            period=rec.get("period", ""),
            fiscal_year=rec.get("fiscal_year", 0) or 0,
            metric=rec.get("line_item_code") or rec.get("metric", ""),
            metric_label=rec.get("line_item_label") or rec.get("metric_label", ""),
            value=float(rec.get("value") or 0),
            value_display=rec.get("value_display", ""),
            unit=rec.get("unit", "vnd_bn"),
            fact_id=rec.get("fact_id", ""),
            source_id=rec.get("source_id", ""),
            source_uri=rec.get("source_uri", ""),
            source_title=rec.get("source_title", ""),
            source_tier=rec.get("source_tier"),
            tier_label=rec.get("tier_label", ""),
            published_at=rec.get("published_at", ""),
            reliability_tier=rec.get("reliability_tier"),
            is_derived=rec.get("is_derived", False),
            official_document_id=rec.get("official_document_id"),
            reconciliation_status=rec.get("reconciliation_status", "missing_official"),
        )
    return out


def citation_map_to_legacy_dict(cmap: CitationMap) -> dict[str, dict]:
    """Convert CitationMap to the legacy dict format used by generate_report.py.

    Adds backward-compat aliases so code using `v['line_item_label']`,
    `v['line_item_code']`, and `v['fiscal_year']` continues to work.
    """
    result = {}
    for key, rec in cmap.items():
        d = rec.to_dict()
        # Legacy aliases used throughout generate_report.py
        d["line_item_code"] = rec.metric
        d["line_item_label"] = rec.metric_label
        d["fiscal_year"] = rec.fiscal_year
        result[key] = d
    return result
