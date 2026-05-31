"""
OCR Reconciliation Gate.

Compares OCR-derived CandidateFacts against a secondary structured source
(CafeF/vnstock API) to determine whether extracted values agree.

Trust policy:
- Official OCR has higher authority but lower extraction reliability.
- CafeF/API has lower authority but higher structural cleanliness.
- Conflicted facts must NOT be auto-promoted; they are stored for manual review.

Only facts with validation_status == "passed" are processed. Facts with
validation_status != "passed" are skipped (reconciliation_status stays
"not_checked").

Decision rules:
- "matched"                   → decision = "promote_eligible"
- "conflicted"                → decision = "blocked_conflict"
- "missing_secondary_source"  → decision = "needs_review"  (do NOT auto-fail)
"""

from __future__ import annotations

import dataclasses
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from backend.documents.ocr_candidate_facts import CandidateFact

# ---------------------------------------------------------------------------
# Tolerance defaults
# ---------------------------------------------------------------------------

DEFAULT_ABSOLUTE_TOLERANCE_VND_BN: float = 1.0   # 1 billion VND in tỷ VND units
DEFAULT_RELATIVE_TOLERANCE: float = 0.005         # 0.5 %

# ---------------------------------------------------------------------------
# ReconciliationRecord dataclass
# ---------------------------------------------------------------------------

_VALID_STATUSES = frozenset({"matched", "conflicted", "missing_secondary_source"})
_VALID_DECISIONS = frozenset({"promote_eligible", "blocked_conflict", "needs_review"})


@dataclass
class ReconciliationRecord:
    """Result of comparing one CandidateFact against a secondary structured source.

    Fields:
        ticker              Ticker symbol (e.g. "DHG").
        fiscal_year         Four-digit fiscal year (e.g. 2021).
        metric_id           Canonical dot-notation metric id (e.g. "revenue.net").
        period_type         Period type (e.g. "FY", "H1").
        ocr_value           The normalized_value from the CandidateFact (tỷ VND).
        secondary_value     The value from the secondary source, or None if absent.
        absolute_diff       |ocr_value - secondary_value|, or None if no secondary.
        relative_diff       absolute_diff / |secondary_value|, or None if no secondary
                            or secondary_value == 0.
        ocr_source          document_id from the CandidateFact.
        secondary_source    Name of the secondary source (e.g. "cafef", "vnstock").
        status              "matched" | "conflicted" | "missing_secondary_source".
        decision            "promote_eligible" | "blocked_conflict" | "needs_review".
    """

    ticker: str
    fiscal_year: int
    metric_id: str
    period_type: str
    ocr_value: float
    secondary_value: Optional[float]
    absolute_diff: Optional[float]
    relative_diff: Optional[float]
    ocr_source: str           # document_id
    secondary_source: str     # "cafef" | "vnstock" | ...
    status: str               # "matched" | "conflicted" | "missing_secondary_source"
    decision: str             # "promote_eligible" | "blocked_conflict" | "needs_review"


# ---------------------------------------------------------------------------
# Internal tolerance check
# ---------------------------------------------------------------------------


def _within_tolerance(
    ocr_value: float,
    secondary_value: float,
    abs_tol: float,
    rel_tol: float,
) -> bool:
    """Return True if the two values are within the combined tolerance.

    A value is "matched" when:
        |ocr - secondary| <= max(abs_tol, |secondary| * rel_tol)

    This mirrors the classic numpy.allclose semantics but for a single pair.
    """
    threshold = max(abs_tol, abs(secondary_value) * rel_tol)
    return abs(ocr_value - secondary_value) <= threshold


# ---------------------------------------------------------------------------
# Core reconciliation function
# ---------------------------------------------------------------------------


def reconcile_candidate_facts(
    facts: list[CandidateFact],
    secondary_source: dict[tuple[str, int, str, str], float],
    secondary_source_name: str = "secondary",
    abs_tolerance_vnd_bn: float = DEFAULT_ABSOLUTE_TOLERANCE_VND_BN,
    rel_tolerance: float = DEFAULT_RELATIVE_TOLERANCE,
) -> list[ReconciliationRecord]:
    """Reconcile OCR candidate facts against a secondary structured source.

    Mutates each fact's reconciliation_status in place.
    Only processes facts where validation_status == "passed".

    Args:
        facts:               List of CandidateFact (mutated in place).
        secondary_source:    Dict mapping (ticker, fiscal_year, period_type, metric_id)
                             → normalized_value_vnd_bn.
        secondary_source_name: Human-readable name for the secondary source
                             (recorded in ReconciliationRecord.secondary_source).
        abs_tolerance_vnd_bn: Absolute tolerance in tỷ VND (default 1.0).
        rel_tolerance:       Relative tolerance as a fraction (default 0.005 = 0.5 %).

    Returns:
        List of ReconciliationRecord, one for each processed (passed) fact,
        in the same order as the input list.
    """
    records: list[ReconciliationRecord] = []

    for fact in facts:
        # Only reconcile facts that passed validation
        if fact.validation_status != "passed":
            continue

        key = (fact.ticker, fact.fiscal_year, fact.period_type, fact.metric_id)
        ocr_val = fact.normalized_value

        if key not in secondary_source:
            # No secondary data available for this metric
            fact.reconciliation_status = "missing_secondary_source"
            records.append(
                ReconciliationRecord(
                    ticker=fact.ticker,
                    fiscal_year=fact.fiscal_year,
                    metric_id=fact.metric_id,
                    period_type=fact.period_type,
                    ocr_value=ocr_val,
                    secondary_value=None,
                    absolute_diff=None,
                    relative_diff=None,
                    ocr_source=fact.document_id,
                    secondary_source=secondary_source_name,
                    status="missing_secondary_source",
                    decision="needs_review",
                )
            )
            continue

        sec_val = secondary_source[key]

        # Compute differences
        abs_diff = abs(ocr_val - sec_val)
        if sec_val != 0 and math.isfinite(sec_val):
            rel_diff: Optional[float] = abs_diff / abs(sec_val)
        else:
            rel_diff = None

        matched = _within_tolerance(ocr_val, sec_val, abs_tolerance_vnd_bn, rel_tolerance)

        if matched:
            status = "matched"
            decision = "promote_eligible"
        else:
            status = "conflicted"
            decision = "blocked_conflict"

        fact.reconciliation_status = status

        records.append(
            ReconciliationRecord(
                ticker=fact.ticker,
                fiscal_year=fact.fiscal_year,
                metric_id=fact.metric_id,
                period_type=fact.period_type,
                ocr_value=ocr_val,
                secondary_value=sec_val,
                absolute_diff=abs_diff,
                relative_diff=rel_diff,
                ocr_source=fact.document_id,
                secondary_source=secondary_source_name,
                status=status,
                decision=decision,
            )
        )

    return records


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------


def save_reconciliation_report(
    records: list[ReconciliationRecord],
    ticker: str,
    fiscal_year: int,
    base_dir: Path = Path("data/reconciliation"),
) -> Path:
    """Save reconciliation report to data/reconciliation/{ticker}/{fiscal_year}/ocr_vs_structured.json.

    The file is a JSON object with metadata and a "records" array.

    Args:
        records:    List of ReconciliationRecord to persist.
        ticker:     Ticker symbol (used as directory name).
        fiscal_year: Fiscal year (used as directory name).
        base_dir:   Base directory for reconciliation reports.

    Returns:
        Resolved path to the saved JSON file.
    """
    out_dir = Path(base_dir) / ticker / str(fiscal_year)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "ocr_vs_structured.json"

    payload = {
        "ticker": ticker,
        "fiscal_year": fiscal_year,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_records": len(records),
        "summary": _build_summary(records),
        "records": [dataclasses.asdict(r) for r in records],
    }

    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out_path.resolve()


def load_reconciliation_report(
    ticker: str,
    fiscal_year: int,
    base_dir: Path = Path("data/reconciliation"),
) -> list[ReconciliationRecord]:
    """Load reconciliation report from disk.

    Args:
        ticker:      Ticker symbol.
        fiscal_year: Fiscal year.
        base_dir:    Base directory for reconciliation reports.

    Returns:
        List of ReconciliationRecord.

    Raises:
        FileNotFoundError: If the report file does not exist.
        ValueError: If the file cannot be parsed or contains invalid data.
    """
    report_path = Path(base_dir) / ticker / str(fiscal_year) / "ocr_vs_structured.json"
    if not report_path.exists():
        raise FileNotFoundError(
            f"Reconciliation report not found: {report_path}"
        )

    try:
        raw = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Cannot parse reconciliation report at {report_path}: {exc}"
        ) from exc

    records: list[ReconciliationRecord] = []
    for item in raw.get("records", []):
        try:
            records.append(ReconciliationRecord(**item))
        except TypeError as exc:
            raise ValueError(f"Invalid ReconciliationRecord: {exc}") from exc
    return records


# ---------------------------------------------------------------------------
# Internal summary helper
# ---------------------------------------------------------------------------


def _build_summary(records: list[ReconciliationRecord]) -> dict:
    """Build a counts summary dict from a list of ReconciliationRecord."""
    counts: dict[str, int] = {
        "matched": 0,
        "conflicted": 0,
        "missing_secondary_source": 0,
    }
    for r in records:
        counts[r.status] = counts.get(r.status, 0) + 1

    total = len(records)
    return {
        "total": total,
        "matched": counts["matched"],
        "conflicted": counts["conflicted"],
        "missing_secondary_source": counts["missing_secondary_source"],
        "promote_eligible_count": counts["matched"],
        "blocked_conflict_count": counts["conflicted"],
        "needs_review_count": counts["missing_secondary_source"],
    }
