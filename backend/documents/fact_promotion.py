"""
Fact Promotion Gate.

Promotes CandidateFact objects from the OCR staging layer to canonical FactEntry
objects that can be stored in the FactTable for downstream valuation and reporting.

Promotion is gated behind three hard requirements:
  1. validation_status == "passed"
  2. reconciliation_status in {"matched", "missing_secondary_source"}
  3. confidence >= min_confidence (default 0.80)

For CRITICAL_METRICS, "matched" reconciliation is required by default
(require_matched_for_critical=True), since these metrics drive valuation directly.

Idempotency: promote_candidate_facts() will not create duplicates. A fact is
considered a duplicate if (metric_id, period_key) already appears in the
accumulated FactTable for the current batch.

Source mapping: OCR → FactEntry
  source_tier = 2  (official PDF OCR — below Tier 0/1 audited statements but
                    above Tier 3 API data)
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from backend.documents.ocr_candidate_facts import CandidateFact
from backend.facts.normalizer import FactEntry, FactTable


# ---------------------------------------------------------------------------
# Critical metric set — these must have reconciliation_status == "matched"
# when require_matched_for_critical=True
# ---------------------------------------------------------------------------

CRITICAL_METRICS: frozenset[str] = frozenset({
    "revenue.net",
    "gross_profit.total",
    "operating_profit.total",
    "profit_before_tax.total",
    "tax_expense.total",
    "net_income.parent",
    "eps.basic",
    "total_assets.total",
    "equity.total",
    "cash_and_equivalents.total",
    "borrowings.total",
    "operating_cash_flow.total",
    "capex.total",
})

# Default minimum confidence threshold for promotion
MIN_CONFIDENCE_DEFAULT: float = 0.80

# OCR source tier: official PDF OCR is Tier 2
_OCR_SOURCE_TIER: int = 2


# ---------------------------------------------------------------------------
# PromotionResult dataclass
# ---------------------------------------------------------------------------


@dataclass
class PromotionResult:
    """Result of attempting to promote a single CandidateFact.

    Fields:
        fact        The CandidateFact that was evaluated.
        promoted    True if the fact was promoted to a FactEntry.
        reason      "promoted" if promoted, otherwise a short explanation of
                    why the fact was blocked.
        fact_entry  The FactEntry created if promoted, None otherwise.
    """

    fact: CandidateFact
    promoted: bool
    reason: str                        # "promoted" | why blocked
    fact_entry: Optional[FactEntry]    # None if not promoted


# ---------------------------------------------------------------------------
# Period key helper
# ---------------------------------------------------------------------------


def _period_key(fiscal_year: int, period_type: str) -> str:
    """Build period key e.g. "2021FY" from fiscal_year=2021, period_type="FY"."""
    return f"{fiscal_year}{period_type}"


# ---------------------------------------------------------------------------
# can_promote
# ---------------------------------------------------------------------------


def can_promote(
    fact: CandidateFact,
    min_confidence: float = MIN_CONFIDENCE_DEFAULT,
    require_matched_for_critical: bool = True,
) -> tuple[bool, str]:
    """Check if a CandidateFact meets all promotion criteria.

    Rules applied in order:
      1. validation_status must be "passed".
      2. reconciliation_status must not be "not_checked" or "conflicted".
         Allowed values: "matched", "missing_secondary_source".
      3. confidence must be >= min_confidence.
      4. All required source metadata must be present: document_id, page_number,
         metric_id, ticker, fiscal_year.
      5. For CRITICAL_METRICS with require_matched_for_critical=True, the
         reconciliation_status must be "matched" (not "missing_secondary_source").

    Args:
        fact:                           The CandidateFact to evaluate.
        min_confidence:                 Minimum confidence threshold (default 0.80).
        require_matched_for_critical:   If True, critical metrics must be "matched"
                                        (not just "missing_secondary_source").

    Returns:
        (eligible, reason) tuple. reason is "eligible" when True, or a short
        string explaining why the fact was blocked when False.
    """
    # Rule 1: validation must have passed
    if fact.validation_status != "passed":
        return False, f"validation_status={fact.validation_status!r} (requires 'passed')"

    # Rule 2: reconciliation must be in allowed set
    allowed_reconciliation = {"matched", "missing_secondary_source"}
    if fact.reconciliation_status not in allowed_reconciliation:
        return False, (
            f"reconciliation_status={fact.reconciliation_status!r} "
            f"(requires one of {sorted(allowed_reconciliation)})"
        )

    # Rule 3: confidence threshold
    if fact.confidence < min_confidence:
        return False, (
            f"confidence={fact.confidence:.3f} < min_confidence={min_confidence:.3f}"
        )

    # Rule 4: required source metadata
    missing_fields: list[str] = []
    if not fact.document_id:
        missing_fields.append("document_id")
    if not fact.page_number:
        missing_fields.append("page_number")
    if not fact.metric_id:
        missing_fields.append("metric_id")
    if not fact.ticker:
        missing_fields.append("ticker")
    if not fact.fiscal_year:
        missing_fields.append("fiscal_year")
    if missing_fields:
        return False, f"missing required source metadata: {missing_fields}"

    # Rule 5: critical metrics need "matched" reconciliation
    if require_matched_for_critical and fact.metric_id in CRITICAL_METRICS:
        if fact.reconciliation_status != "matched":
            return False, (
                f"critical metric {fact.metric_id!r} requires reconciliation_status='matched', "
                f"got {fact.reconciliation_status!r}"
            )

    return True, "eligible"


# ---------------------------------------------------------------------------
# promote_candidate_fact (single)
# ---------------------------------------------------------------------------


def promote_candidate_fact(
    fact: CandidateFact,
    min_confidence: float = MIN_CONFIDENCE_DEFAULT,
    require_matched_for_critical: bool = True,
) -> PromotionResult:
    """Attempt to promote a single CandidateFact to a FactEntry.

    If eligible:
      - Creates a FactEntry with full source provenance.
      - Sets fact.promotion_status = "promoted".
      - Returns PromotionResult(promoted=True, fact_entry=<FactEntry>).

    If not eligible:
      - Does NOT modify fact.promotion_status.
      - Returns PromotionResult(promoted=False, reason=<why>, fact_entry=None).

    This function does NOT modify any external state (no FactTable writes).
    The caller is responsible for placing the returned FactEntry.

    Args:
        fact:                           The CandidateFact to promote.
        min_confidence:                 Minimum confidence threshold (default 0.80).
        require_matched_for_critical:   If True, critical metrics must be "matched".

    Returns:
        PromotionResult with promoted=True/False and reason.
    """
    eligible, reason = can_promote(fact, min_confidence, require_matched_for_critical)

    if not eligible:
        return PromotionResult(fact=fact, promoted=False, reason=reason, fact_entry=None)

    # Build the FactEntry — source_tier=2 for official PDF OCR
    entry = FactEntry(
        value=fact.normalized_value,
        fact_id=fact.candidate_fact_id,
        source_id=fact.document_id,
        source_uri=fact.document_id,
        source_title=f"OCR:{fact.document_id}:p{fact.page_number}",
        source_tier=_OCR_SOURCE_TIER,
        reliability_tier=_OCR_SOURCE_TIER,
        confidence=fact.confidence,
        connector_version=fact.parser_version,
        ingested_at=datetime.now(timezone.utc),
    )

    # Mark the fact as promoted
    fact.promotion_status = "promoted"

    return PromotionResult(fact=fact, promoted=True, reason="promoted", fact_entry=entry)


# ---------------------------------------------------------------------------
# promote_candidate_facts (batch, idempotent)
# ---------------------------------------------------------------------------


def promote_candidate_facts(
    facts: list[CandidateFact],
    min_confidence: float = MIN_CONFIDENCE_DEFAULT,
    require_matched_for_critical: bool = True,
) -> tuple[FactTable, list[PromotionResult]]:
    """Promote all eligible facts from a list to a FactTable.

    Idempotency: if a (metric_id, period_key) pair is already in the accumulated
    FactTable from this batch, the second occurrence is blocked with reason
    "duplicate: (metric_id, period_key) already promoted in this batch".

    Period key is constructed as f"{fiscal_year}{period_type}" e.g. "2021FY".

    Args:
        facts:                          List of CandidateFact to evaluate.
        min_confidence:                 Minimum confidence threshold (default 0.80).
        require_matched_for_critical:   If True, critical metrics must be "matched".

    Returns:
        (fact_table, results) where:
          fact_table: FactTable indexed by [metric_id][period_key].
          results:    List of PromotionResult, one per input fact, in order.
    """
    fact_table: FactTable = {}
    results: list[PromotionResult] = []

    for fact in facts:
        period = _period_key(fact.fiscal_year, fact.period_type)
        metric = fact.metric_id

        # Idempotency check: if (metric, period) already in this batch, block
        if metric in fact_table and period in fact_table[metric]:
            results.append(
                PromotionResult(
                    fact=fact,
                    promoted=False,
                    reason=f"duplicate: ({metric!r}, {period!r}) already promoted in this batch",
                    fact_entry=None,
                )
            )
            continue

        # Attempt promotion
        result = promote_candidate_fact(fact, min_confidence, require_matched_for_critical)
        results.append(result)

        if result.promoted and result.fact_entry is not None:
            if metric not in fact_table:
                fact_table[metric] = {}
            fact_table[metric][period] = result.fact_entry

    return fact_table, results


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------


def save_promoted_facts(
    fact_table: FactTable,
    ticker: str,
    fiscal_year: int,
    base_dir: Path = Path("data/promoted_facts"),
) -> Path:
    """Persist promoted facts to data/promoted_facts/{ticker}/{fiscal_year}/promoted_facts.json.

    Serializes the FactTable as a JSON object:
    {
        "ticker": "DHG",
        "fiscal_year": 2021,
        "generated_at": "<ISO8601>",
        "metrics": {
            "revenue.net": {
                "2021FY": { ...FactEntry fields... }
            }
        }
    }

    FactEntry.ingested_at (datetime) is serialized to ISO 8601 string.

    Args:
        fact_table:  FactTable to persist.
        ticker:      Ticker symbol (used for directory path).
        fiscal_year: Fiscal year (used for directory path).
        base_dir:    Base directory for promoted facts storage.

    Returns:
        Resolved path to the saved JSON file.
    """
    out_dir = Path(base_dir) / ticker / str(fiscal_year)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "promoted_facts.json"

    # Serialize FactTable — FactEntry is a frozen dataclass, convert manually
    metrics_payload: dict = {}
    for metric_id, periods in fact_table.items():
        metrics_payload[metric_id] = {}
        for period_key, entry in periods.items():
            metrics_payload[metric_id][period_key] = _serialize_fact_entry(entry)

    payload = {
        "ticker": ticker,
        "fiscal_year": fiscal_year,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_facts": sum(len(p) for p in fact_table.values()),
        "metrics": metrics_payload,
    }

    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out_path.resolve()


def load_promoted_facts(
    ticker: str,
    fiscal_year: int,
    base_dir: Path = Path("data/promoted_facts"),
) -> FactTable:
    """Load promoted facts from disk.

    Args:
        ticker:      Ticker symbol.
        fiscal_year: Fiscal year.
        base_dir:    Base directory for promoted facts storage.

    Returns:
        FactTable deserialized from disk. Returns empty FactTable if the file
        does not exist (not an error — first-run or no facts promoted yet).

    Raises:
        ValueError: If the file exists but cannot be parsed.
    """
    file_path = Path(base_dir) / ticker / str(fiscal_year) / "promoted_facts.json"
    if not file_path.exists():
        return {}

    try:
        raw = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Cannot parse promoted facts JSON at {file_path}: {exc}"
        ) from exc

    fact_table: FactTable = {}
    for metric_id, periods in raw.get("metrics", {}).items():
        fact_table[metric_id] = {}
        for period_key, entry_dict in periods.items():
            fact_table[metric_id][period_key] = _deserialize_fact_entry(entry_dict)

    return fact_table


# ---------------------------------------------------------------------------
# Internal serialization helpers
# ---------------------------------------------------------------------------


def _serialize_fact_entry(entry: FactEntry) -> dict:
    """Convert a FactEntry to a JSON-serializable dict."""
    ingested_str: Optional[str] = None
    if entry.ingested_at is not None:
        if isinstance(entry.ingested_at, datetime):
            ingested_str = entry.ingested_at.isoformat()
        else:
            ingested_str = str(entry.ingested_at)

    return {
        "value": entry.value,
        "fact_id": entry.fact_id,
        "source_id": entry.source_id,
        "source_uri": entry.source_uri,
        "source_title": entry.source_title,
        "source_tier": entry.source_tier,
        "reliability_tier": entry.reliability_tier,
        "confidence": entry.confidence,
        "connector_version": entry.connector_version,
        "ingested_at": ingested_str,
    }


def _deserialize_fact_entry(d: dict) -> FactEntry:
    """Reconstruct a FactEntry from a deserialized dict."""
    ingested_at: Optional[datetime] = None
    raw_ts = d.get("ingested_at")
    if raw_ts is not None:
        try:
            ingested_at = datetime.fromisoformat(raw_ts)
        except (ValueError, TypeError):
            ingested_at = None

    return FactEntry(
        value=float(d["value"]),
        fact_id=d.get("fact_id"),
        source_id=d.get("source_id"),
        source_uri=d.get("source_uri") or "",
        source_title=d.get("source_title") or "",
        source_tier=d.get("source_tier"),
        reliability_tier=d.get("reliability_tier"),
        confidence=d.get("confidence"),
        connector_version=d.get("connector_version") or "",
        ingested_at=ingested_at,
    )
