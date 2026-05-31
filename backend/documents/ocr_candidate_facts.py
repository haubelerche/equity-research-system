"""
OCR Candidate Fact staging layer.

CandidateFact holds OCR-derived facts BEFORE they may be promoted to
canonical financial facts. Promotion is NEVER automatic — every fact starts
with promotion_status = "blocked".

Design rules enforced here:
- No imports from any canonical facts module (no DB writes, no financial_facts).
- All facts must be created through create_candidate_fact() — never directly
  instantiating CandidateFact in external code.
- from_extracted_rows() is the bridge from raw OCR extraction to this layer.
"""

from __future__ import annotations

import dataclasses
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Staging status constants
# ---------------------------------------------------------------------------

VALIDATION_STATUSES = frozenset({"pending", "passed", "failed"})
RECONCILIATION_STATUSES = frozenset(
    {"not_checked", "matched", "conflicted", "missing_secondary_source"}
)
PROMOTION_STATUSES = frozenset({"blocked", "promoted"})


# ---------------------------------------------------------------------------
# CandidateFact dataclass
# ---------------------------------------------------------------------------


@dataclass
class CandidateFact:
    """A financial fact extracted via OCR, held in the staging layer.

    All facts start with:
        validation_status    = "pending"
        reconciliation_status = "not_checked"
        promotion_status     = "blocked"

    They must go through explicit validation and reconciliation before
    promotion_status can be changed to "promoted".
    """

    candidate_fact_id: str          # uuid4 hex
    ocr_run_id: str
    document_id: str
    ticker: str
    fiscal_year: int
    period_type: str                # "FY" | "H1" | "H2" | "Q1" etc.
    page_number: int
    statement_type: str             # "income_statement" | "balance_sheet" | "cash_flow_statement"
    raw_label: str                  # original Vietnamese label text
    normalized_label: str           # slugged/normalized label
    metric_id: str                  # canonical dot-notation e.g. "revenue.net"
    raw_value: str                  # original raw string from OCR
    normalized_value: float         # parsed float value
    unit: str                       # "vnd_bn" | "vnd"
    currency: str                   # "VND"
    confidence: float               # 0.0–1.0
    mapping_rule_id: str            # which pattern matched (from financial_metric_dictionary.yaml)
    parser_version: str             # e.g. "1.0.0"
    source_type: str                # always "official_pdf_ocr"
    validation_status: str          # "pending" | "passed" | "failed"
    reconciliation_status: str      # "not_checked" | "matched" | "conflicted" | "missing_secondary_source"
    promotion_status: str           # "blocked" | "promoted"
    warnings: list[str] = field(default_factory=list)
    created_at: str = ""            # ISO8601


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_candidate_fact(
    ocr_run_id: str,
    document_id: str,
    ticker: str,
    fiscal_year: int,
    page_number: int,
    statement_type: str,
    raw_label: str,
    normalized_label: str,
    metric_id: str,
    raw_value: str,
    normalized_value: float,
    unit: str,
    confidence: float,
    mapping_rule_id: str = "",
    period_type: str = "FY",
    parser_version: str = "1.0.0",
) -> CandidateFact:
    """Create a new CandidateFact with default staging statuses.

    Always initializes with:
        validation_status     = "pending"
        reconciliation_status = "not_checked"
        promotion_status      = "blocked"    ← promotion is NEVER automatic
        source_type           = "official_pdf_ocr"
        currency              = "VND"
    """
    return CandidateFact(
        candidate_fact_id=uuid.uuid4().hex,
        ocr_run_id=ocr_run_id,
        document_id=document_id,
        ticker=ticker,
        fiscal_year=fiscal_year,
        period_type=period_type,
        page_number=page_number,
        statement_type=statement_type,
        raw_label=raw_label,
        normalized_label=normalized_label,
        metric_id=metric_id,
        raw_value=raw_value,
        normalized_value=normalized_value,
        unit=unit,
        currency="VND",
        confidence=confidence,
        mapping_rule_id=mapping_rule_id,
        parser_version=parser_version,
        source_type="official_pdf_ocr",
        validation_status="pending",
        reconciliation_status="not_checked",
        promotion_status="blocked",
        warnings=[],
        created_at=datetime.now(timezone.utc).isoformat(),
    )


# ---------------------------------------------------------------------------
# Bridge from raw OCR extraction
# ---------------------------------------------------------------------------


def from_extracted_rows(
    rows: list,  # list of ExtractedRow from pdf_extractor.py
    ocr_run_id: str,
    document_id: str,
    confidence: float = 0.7,
) -> list[CandidateFact]:
    """Convert ExtractedRow objects into CandidateFact staging entries.

    This is the bridge between raw OCR extraction and the staging layer.
    Does NOT write to financial_facts or any canonical store.

    Each ExtractedRow is passed through create_candidate_fact() so that
    all staging-status defaults are applied uniformly.

    Args:
        rows: List of ExtractedRow from pdf_extractor.py.
        ocr_run_id: Identifier for the OCR run that produced these rows.
        document_id: Identifier for the source document.
        confidence: Default OCR confidence to assign (0.0–1.0).

    Returns:
        List of CandidateFact, all with promotion_status="blocked".
    """
    facts: list[CandidateFact] = []
    for row in rows:
        fact = create_candidate_fact(
            ocr_run_id=ocr_run_id,
            document_id=document_id,
            ticker=row.ticker,
            fiscal_year=row.fiscal_year,
            page_number=row.page_number,
            statement_type=row.statement_type,
            raw_label=row.extracted_text,
            normalized_label=row.extracted_text,   # caller may re-slug if needed
            metric_id=row.metric_id,
            raw_value=str(row.value),
            normalized_value=float(row.value),
            unit=row.unit,
            confidence=confidence,
            mapping_rule_id="",                    # pattern rule id not stored on ExtractedRow
            period_type=row.period_type,
            parser_version="1.0.0",
        )
        facts.append(fact)
    return facts


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------


def save_candidate_facts(facts: list[CandidateFact], output_path: Path) -> Path:
    """Persist candidate facts to a JSON file for inspection.

    Uses dataclasses.asdict() for serialization. The output file is a
    JSON array of objects.

    Args:
        facts: List of CandidateFact to save.
        output_path: Destination file path (.json).

    Returns:
        The resolved output_path.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [dataclasses.asdict(f) for f in facts]
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path.resolve()


def load_candidate_facts(input_path: Path) -> list[CandidateFact]:
    """Load candidate facts from a JSON file produced by save_candidate_facts().

    Args:
        input_path: Path to the JSON file.

    Returns:
        List of CandidateFact instances.

    Raises:
        FileNotFoundError: If input_path does not exist.
        ValueError: If the file cannot be parsed or contains invalid data.
    """
    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"Candidate facts file not found: {input_path}")
    try:
        raw = json.loads(input_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Cannot parse candidate facts JSON at {input_path}: {exc}") from exc

    facts: list[CandidateFact] = []
    for item in raw:
        # Ensure warnings is a list (guard against None in older serializations)
        if item.get("warnings") is None:
            item["warnings"] = []
        try:
            facts.append(CandidateFact(**item))
        except TypeError as exc:
            raise ValueError(f"Invalid CandidateFact record: {exc}") from exc
    return facts


# ---------------------------------------------------------------------------
# Filtering helpers
# ---------------------------------------------------------------------------


def filter_by_status(
    facts: list[CandidateFact],
    validation_status: Optional[str] = None,
    reconciliation_status: Optional[str] = None,
    promotion_status: Optional[str] = None,
) -> list[CandidateFact]:
    """Filter facts by one or more status fields.

    Only filters by a field if the corresponding argument is not None.
    Multiple arguments are combined with AND logic.

    Args:
        facts: Input list of CandidateFact.
        validation_status: Filter to this validation_status if provided.
        reconciliation_status: Filter to this reconciliation_status if provided.
        promotion_status: Filter to this promotion_status if provided.

    Returns:
        Filtered list (may be empty).
    """
    result = facts
    if validation_status is not None:
        result = [f for f in result if f.validation_status == validation_status]
    if reconciliation_status is not None:
        result = [f for f in result if f.reconciliation_status == reconciliation_status]
    if promotion_status is not None:
        result = [f for f in result if f.promotion_status == promotion_status]
    return result
