"""Deterministic fact normalization and derived metric computation.

Takes a list of raw FinancialFact dicts from the DB and returns a structured
FactTable: a dict keyed by line_item_code → period_key → FactEntry.

FactEntry carries the numeric value plus full source provenance (source_id,
source_uri, source_tier, confidence, etc.) so every downstream consumer —
valuation, report generation, citation builder — can trace each number back
to its origin without a DB round-trip.

Key invariant: `build_fact_table()` NEVER returns bare floats.
All callers must access the numeric value via `entry.value`.

Derived metrics (not stored in DB — computed here):
  free_cash_flow.total  = operating_cash_flow.total + capex.total
  gross_margin          = gross_profit.total / revenue.net
  ebitda_margin         = ebitda.total / revenue.net
  net_margin            = net_income.parent / revenue.net
  debt_to_equity        = total_debt.ending / equity.parent
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class FactEntry:
    """A single canonical fact value with full source provenance.

    Derived metrics (computed from other facts) have source_id=None and
    source_tier=None to indicate they are not directly sourced.
    """
    value: float
    fact_id: str | None = None
    source_id: str | None = None
    source_uri: str = ""
    source_title: str = ""
    source_tier: int | None = None      # None for derived metrics
    reliability_tier: int | None = None  # legacy field from ingest.sources
    confidence: float | None = None
    connector_version: str = ""
    ingested_at: datetime | None = None

    def is_derived(self) -> bool:
        return self.source_id is None


# FactTable carries FactEntry objects — never bare floats.
FactTable = dict[str, dict[str, FactEntry]]


def _period_key(fiscal_year: int, fiscal_period: str) -> str:
    return f"{fiscal_year}{fiscal_period}"


# ── Conflict / reconciliation records (in-memory, not DB) ─────────────────────

@dataclass
class ConflictRecord:
    """Records when 2+ sources disagree on the same (metric, period)."""
    ticker: str
    period: str
    metric: str
    candidate_values: dict[str, float]   # source_id → value
    selected_source_id: str | None
    variance_pct: float
    requires_review: bool                # True when variance > HIGH_VARIANCE_THRESHOLD
    decision_reason: str


_CONFLICT_THRESHOLD_PCT = 2.0     # flag if sources differ by > 2%
_HIGH_VARIANCE_THRESHOLD_PCT = 10.0  # require manual review if > 10%


def _compute_variance_pct(values: list[float]) -> float:
    """Max spread as a fraction of the max absolute value. Returns 0.0 for ≤1 value."""
    if len(values) < 2:
        return 0.0
    max_abs = max(abs(v) for v in values)
    if max_abs == 0.0:
        return 0.0
    return (max(values) - min(values)) / max_abs * 100.0


# ── Core normalizer ────────────────────────────────────────────────────────────

def build_fact_table(raw_facts: list[dict[str, Any]]) -> FactTable:
    """Convert flat fact rows from DB into FactTable: taxonomy_key → period → FactEntry.

    Selection rule: when multiple rows exist for the same (taxonomy_key, period),
    prefer the row with the lowest source_tier (Tier 0 beats Tier 3), then
    highest confidence, then latest ingested_at.

    Each winning value is wrapped in a FactEntry that preserves full source
    provenance for downstream citation and gate checks.
    """
    # Collect best row per (taxonomy_key, period)
    best: dict[tuple[str, str], dict[str, Any]] = {}
    for row in raw_facts:
        code = row.get("line_item_code") or row.get("taxonomy_key", "")
        key = (code, _period_key(row["fiscal_year"], row["fiscal_period"]))
        existing = best.get(key)
        if existing is None:
            best[key] = row
        else:
            # Lower source_tier wins (Tier 0 = audited > Tier 3 = API)
            row_tier = row.get("source_tier") if row.get("source_tier") is not None else 3
            ex_tier = existing.get("source_tier") if existing.get("source_tier") is not None else 3
            if row_tier < ex_tier:
                best[key] = row
            elif row_tier == ex_tier:
                row_conf = row.get("confidence") or 0.0
                ex_conf = existing.get("confidence") or 0.0
                if row_conf > ex_conf:
                    best[key] = row
                elif row_conf == ex_conf:
                    if str(row.get("ingested_at", "")) > str(existing.get("ingested_at", "")):
                        best[key] = row

    table: FactTable = {}
    for (line_item_code, period), row in best.items():
        if line_item_code not in table:
            table[line_item_code] = {}
        table[line_item_code][period] = FactEntry(
            value=float(row["value"]),
            fact_id=str(row.get("id") or row.get("fact_id") or ""),
            source_id=row.get("source_id"),
            source_uri=row.get("src_uri") or row.get("source_uri") or "",
            source_title=row.get("src_title") or row.get("source_title") or "",
            source_tier=row.get("source_tier"),
            reliability_tier=row.get("reliability_tier") or row.get("src_reliability_tier"),
            confidence=row.get("confidence"),
            connector_version=row.get("connector_version") or "",
            ingested_at=row.get("ingested_at"),
        )

    return table


def build_source_conflict_report(
    ticker: str,
    raw_facts: list[dict[str, Any]],
) -> list[ConflictRecord]:
    """Return a list of ConflictRecord for any (metric, period) with 2+ differing sources.

    Only facts with source_id are included (golden CSV synthetic IDs are compared too).
    Runs entirely in-memory; does not write to DB.
    """
    # Group all observations by (metric, period)
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in raw_facts:
        code = row.get("line_item_code") or row.get("taxonomy_key", "")
        period = _period_key(row["fiscal_year"], row["fiscal_period"])
        groups.setdefault((code, period), []).append(row)

    conflicts: list[ConflictRecord] = []
    for (metric, period), rows in groups.items():
        if len(rows) < 2:
            continue
        # Build source_id → value map (skip rows with identical source_id)
        src_values: dict[str, float] = {}
        for row in rows:
            sid = row.get("source_id") or "unknown"
            src_values[sid] = float(row["value"])

        if len(src_values) < 2:
            continue

        variance = _compute_variance_pct(list(src_values.values()))
        if variance < _CONFLICT_THRESHOLD_PCT:
            continue

        # Select winner using same rule as build_fact_table
        best_row = rows[0]
        for row in rows[1:]:
            row_tier = row.get("source_tier") if row.get("source_tier") is not None else 3
            ex_tier = best_row.get("source_tier") if best_row.get("source_tier") is not None else 3
            if row_tier < ex_tier:
                best_row = row
            elif row_tier == ex_tier:
                if (row.get("confidence") or 0.0) > (best_row.get("confidence") or 0.0):
                    best_row = row

        requires_review = variance >= _HIGH_VARIANCE_THRESHOLD_PCT
        winner_tier = best_row.get("source_tier") if best_row.get("source_tier") is not None else 3
        conflicts.append(ConflictRecord(
            ticker=ticker,
            period=period,
            metric=metric,
            candidate_values=src_values,
            selected_source_id=best_row.get("source_id"),
            variance_pct=round(variance, 4),
            requires_review=requires_review,
            decision_reason=(
                f"Selected source_id={best_row.get('source_id', '?')[:12]}... "
                f"(tier={winner_tier}, confidence={best_row.get('confidence')})"
            ),
        ))

    return conflicts


def build_source_tier_coverage(
    raw_facts: list[dict[str, Any]],
    required_periods: list[str],
) -> dict[str, dict]:
    """Return per-period source tier summary for the coverage gate.

    Returns a dict keyed by period:
        {
            "2023FY": {
                "min_tier": 3,
                "tiers_present": [3],
                "has_tier01": False,
            },
            ...
        }
    """
    period_tiers: dict[str, list[int]] = {p: [] for p in required_periods}
    for row in raw_facts:
        period = _period_key(row["fiscal_year"], row["fiscal_period"])
        if period not in period_tiers:
            continue
        tier = row.get("source_tier") if row.get("source_tier") is not None else 3
        period_tiers[period].append(tier)

    result = {}
    for period, tiers in period_tiers.items():
        if not tiers:
            result[period] = {"min_tier": None, "tiers_present": [], "has_tier01": False}
        else:
            unique = sorted(set(tiers))
            result[period] = {
                "min_tier": min(tiers),
                "tiers_present": unique,
                "has_tier01": any(t <= 1 for t in tiers),
            }
    return result


def build_validation_status_table(raw_facts: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    """Return validation_status for each (taxonomy_key, period).

    Uses same tier→confidence→ingested_at tie-breaking as build_fact_table.
    """
    best: dict[tuple[str, str], dict[str, Any]] = {}
    for row in raw_facts:
        code = row.get("line_item_code") or row.get("taxonomy_key", "")
        key = (code, _period_key(row["fiscal_year"], row["fiscal_period"]))
        existing = best.get(key)
        if existing is None:
            best[key] = row
        else:
            row_tier = row.get("source_tier") if row.get("source_tier") is not None else 3
            ex_tier = existing.get("source_tier") if existing.get("source_tier") is not None else 3
            if row_tier < ex_tier:
                best[key] = row
            elif row_tier == ex_tier:
                row_conf = row.get("confidence") or 0.0
                ex_conf = existing.get("confidence") or 0.0
                if row_conf > ex_conf:
                    best[key] = row
                elif row_conf == ex_conf:
                    if str(row.get("ingested_at", "")) > str(existing.get("ingested_at", "")):
                        best[key] = row

    status_table: dict[str, dict[str, str]] = {}
    for (line_item_code, period), row in best.items():
        if line_item_code not in status_table:
            status_table[line_item_code] = {}
        status_table[line_item_code][period] = str(row.get("validation_status") or "unknown")
    return status_table


# ── Derived metric computation ─────────────────────────────────────────────────

def _safe_div(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None:
        return None
    if denominator == 0.0:
        return None
    return numerator / denominator


def _derived_entry(value: float) -> FactEntry:
    """Create a FactEntry for a derived/computed metric (no DB source)."""
    return FactEntry(value=value, source_id=None, source_tier=None)


def compute_derived(table: FactTable) -> FactTable:
    """Add derived metrics to the table. Operates on a copy — does not mutate input.

    Input and output are both FactTable (dict[str, dict[str, FactEntry]]).
    Derived FactEntry objects have source_id=None and source_tier=None to signal
    that they are computed, not directly sourced.
    """
    derived: FactTable = {}

    # Collect all periods
    all_periods: set[str] = set()
    for periods in table.values():
        all_periods.update(periods.keys())

    for period in sorted(all_periods):
        def get(key: str) -> float | None:
            entry = table.get(key, {}).get(period)
            return entry.value if entry is not None else None

        # free_cash_flow.total = OCF + capex (capex stored negative)
        ocf = get("operating_cash_flow.total")
        capex = get("capex.total")
        if ocf is not None and capex is not None:
            derived.setdefault("free_cash_flow.total", {})[period] = _derived_entry(ocf + capex)

        # gross_margin = gross_profit / revenue
        gp = get("gross_profit.total")
        rev = get("revenue.net")
        gm = _safe_div(gp, rev)
        if gm is not None:
            derived.setdefault("gross_margin", {})[period] = _derived_entry(round(gm, 6))

        # ebitda.total — derive if not directly ingested
        ebitda = get("ebitda.total")
        if ebitda is None:
            dep = get("depreciation.total")
            sga = get("sga.total")
            if gp is not None and sga is not None and dep is not None:
                ebitda = gp + sga + dep
                derived.setdefault("ebitda.total", {})[period] = _derived_entry(round(ebitda, 4))

        # ebitda_margin = ebitda / revenue
        em = _safe_div(ebitda, rev)
        if em is not None:
            derived.setdefault("ebitda_margin", {})[period] = _derived_entry(round(em, 6))

        # net_margin = net_income / revenue
        ni = get("net_income.parent")
        nm = _safe_div(ni, rev)
        if nm is not None:
            derived.setdefault("net_margin", {})[period] = _derived_entry(round(nm, 6))

        # debt_to_equity = total_debt / equity
        debt = get("total_debt.ending")
        eq = get("equity.parent")
        de = _safe_div(debt, eq)
        if de is not None:
            derived.setdefault("debt_to_equity", {})[period] = _derived_entry(round(de, 6))

    # Merge into a new table (do not mutate input)
    merged: FactTable = {k: dict(v) for k, v in table.items()}
    for k, v in derived.items():
        merged[k] = v
    return merged


def periods_sorted(table: FactTable) -> list[str]:
    """Return all period keys in the table, sorted chronologically."""
    all_p: set[str] = set()
    for periods in table.values():
        all_p.update(periods.keys())
    return sorted(all_p)
