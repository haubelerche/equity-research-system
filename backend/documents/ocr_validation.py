"""
OCR Candidate Fact validation gate.

Applies deterministic validation rules to CandidateFact objects from the
OCR staging layer. Validation is a prerequisite before reconciliation or
promotion to canonical financial facts.

Rules applied (in order):
  1. Schema validation  — required fields present, metric_id known, value finite
  2. Period validation  — fiscal_year in range, period_type in allowed set
  3. Financial sanity  — revenue positive, gross/net income ratios, tax≠income check
  4. Duplicate detection — conflict and redundant duplicates within same key group

Cross-fact rules (duplicate detection) are applied by validate_candidate_facts()
only; validate_candidate_fact() applies rules 1–3 for a single fact.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from backend.documents.ocr_candidate_facts import CandidateFact

# ---------------------------------------------------------------------------
# Required metric coverage definition
# ---------------------------------------------------------------------------

REQUIRED_METRICS: dict[str, list[str]] = {
    "income_statement": [
        "revenue.net",
        "gross_profit.total",
        "profit_before_tax.total",
        "tax_expense.total",
        "net_income.parent",
    ],
    "balance_sheet": [
        "total_assets.total",
        "liabilities.total",
        "equity.total",
    ],
}

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FISCAL_YEAR_MIN = 1990
_CURRENT_YEAR = datetime.now(timezone.utc).year

# Path to the metric dictionary YAML (resolved relative to this file's repo root)
_METRIC_DICT_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "financial_metric_dictionary.yaml"
)


# ---------------------------------------------------------------------------
# ValidationResult dataclass
# ---------------------------------------------------------------------------


@dataclass
class ValidationResult:
    """Result of running all applicable validation rules on a single CandidateFact.

    The CandidateFact.validation_status is mutated in place to "passed" or "failed".
    """

    fact: CandidateFact          # mutated in place (validation_status updated)
    passed: bool
    rules_applied: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Metric ID loader
# ---------------------------------------------------------------------------


def load_known_metric_ids() -> frozenset[str]:
    """Load all metric_ids from config/financial_metric_dictionary.yaml.

    Returns:
        A frozenset of canonical metric_id strings.

    Raises:
        FileNotFoundError: If the YAML file cannot be found.
        ValueError: If the YAML file is malformed.
    """
    if not _METRIC_DICT_PATH.exists():
        raise FileNotFoundError(
            f"Financial metric dictionary not found: {_METRIC_DICT_PATH}"
        )
    with _METRIC_DICT_PATH.open(encoding="utf-8") as fh:
        entries = yaml.safe_load(fh)
    if not isinstance(entries, list):
        raise ValueError(
            f"Expected a YAML list in {_METRIC_DICT_PATH}, got {type(entries).__name__}"
        )
    metric_ids: set[str] = set()
    for entry in entries:
        if isinstance(entry, dict) and "metric_id" in entry:
            metric_ids.add(entry["metric_id"])
    return frozenset(metric_ids)


# ---------------------------------------------------------------------------
# Internal rule helpers
# ---------------------------------------------------------------------------


def _rule_schema(
    fact: CandidateFact,
    known_metric_ids: frozenset[str],
    failures: list[str],
    warnings: list[str],
) -> bool:
    """Rule 1 — Schema validation.

    Checks:
    - metric_id non-empty and exists in known_metric_ids
    - normalized_value is finite float
    - ticker, fiscal_year, period_type, statement_type non-empty/non-zero
    """
    ok = True

    # metric_id
    if not fact.metric_id:
        failures.append("schema:metric_id_empty")
        ok = False
    elif fact.metric_id not in known_metric_ids:
        failures.append(f"schema:metric_id_unknown:{fact.metric_id}")
        ok = False

    # normalized_value
    try:
        val = float(fact.normalized_value)
        if math.isnan(val) or math.isinf(val):
            failures.append(f"schema:normalized_value_not_finite:{fact.normalized_value}")
            ok = False
    except (TypeError, ValueError):
        failures.append(f"schema:normalized_value_not_float:{fact.normalized_value!r}")
        ok = False

    # Required string/int fields
    if not fact.ticker:
        failures.append("schema:ticker_empty")
        ok = False
    if not fact.fiscal_year:
        failures.append("schema:fiscal_year_zero")
        ok = False
    if not fact.period_type:
        failures.append("schema:period_type_empty")
        ok = False
    if not fact.statement_type:
        failures.append("schema:statement_type_empty")
        ok = False

    return ok


def _rule_period(
    fact: CandidateFact,
    allowed_period_types: frozenset[str],
    failures: list[str],
    warnings: list[str],
) -> bool:
    """Rule 2 — Period validation.

    Checks:
    - fiscal_year between 1990 and current_year + 1
    - period_type in allowed_period_types
    """
    ok = True

    fy = fact.fiscal_year
    if not isinstance(fy, int) or fy < _FISCAL_YEAR_MIN or fy > _CURRENT_YEAR + 1:
        failures.append(
            f"period:fiscal_year_out_of_range:{fy} (allowed {_FISCAL_YEAR_MIN}-{_CURRENT_YEAR + 1})"
        )
        ok = False

    if fact.period_type not in allowed_period_types:
        failures.append(
            f"period:period_type_not_allowed:{fact.period_type!r} "
            f"(allowed {sorted(allowed_period_types)})"
        )
        ok = False

    return ok


def _rule_financial_sanity(
    fact: CandidateFact,
    all_facts: list[CandidateFact],
    failures: list[str],
    warnings: list[str],
) -> bool:
    """Rule 3 — Financial sanity checks.

    Applied per-statement when multiple metrics are present.

    Checks (applied only when companion metrics are available):
    - revenue.net should be positive (warn if not, fail if < -1e6)
    - gross_profit.total should not exceed revenue.net * 1.5 (warn)
    - net_income.parent should not exceed revenue.net (warn)
    - tax_expense.total must NOT equal net_income.parent within 1%  → FAIL (confusion)
    - total_assets.total >= equity.total (warn if not)
    """
    ok = True

    # Build a quick lookup: metric_id → normalized_value for same ticker/FY/period/statement
    peer: dict[str, float] = {}
    for f in all_facts:
        if (
            f.ticker == fact.ticker
            and f.fiscal_year == fact.fiscal_year
            and f.period_type == fact.period_type
            and f.statement_type == fact.statement_type
            and f.candidate_fact_id != fact.candidate_fact_id
        ):
            try:
                peer[f.metric_id] = float(f.normalized_value)
            except (TypeError, ValueError):
                pass

    try:
        val = float(fact.normalized_value)
    except (TypeError, ValueError):
        # Already caught by schema rule; skip sanity
        return True

    mid = fact.metric_id

    # revenue.net: positive check
    if mid == "revenue.net":
        if val < 0:
            if val < -1_000_000:
                failures.append(f"sanity:revenue_negative_impossible:{val}")
                ok = False
            else:
                warnings.append(f"sanity:revenue_negative_suspicious:{val}")

    # gross_profit.total: should not exceed revenue.net * 1.5
    if mid == "gross_profit.total" and "revenue.net" in peer:
        rev = peer["revenue.net"]
        if rev > 0 and val > rev * 1.5:
            warnings.append(
                f"sanity:gross_profit_exceeds_1.5x_revenue:{val} > {rev * 1.5:.2f}"
            )

    # net_income.parent: should not exceed revenue.net
    if mid == "net_income.parent" and "revenue.net" in peer:
        rev = peer["revenue.net"]
        if rev > 0 and val > rev:
            warnings.append(
                f"sanity:net_income_exceeds_revenue:{val} > {rev}"
            )

    # tax_expense vs net_income confusion — the known false-positive
    # FAIL if same-statement tax_expense.total == net_income.parent within 1%
    if mid == "tax_expense.total" and "net_income.parent" in peer:
        ni = peer["net_income.parent"]
        if ni != 0 and abs(val - ni) / abs(ni) <= 0.01:
            failures.append(
                f"sanity:tax_equals_net_income_confusion:"
                f"tax={val} net_income={ni} (within 1%)"
            )
            ok = False
    if mid == "net_income.parent" and "tax_expense.total" in peer:
        tax = peer["tax_expense.total"]
        if tax != 0 and abs(val - tax) / abs(tax) <= 0.01:
            failures.append(
                f"sanity:net_income_equals_tax_confusion:"
                f"net_income={val} tax={tax} (within 1%)"
            )
            ok = False

    # total_assets.total >= equity.total
    if mid == "total_assets.total" and "equity.total" in peer:
        eq = peer["equity.total"]
        if val < eq:
            warnings.append(
                f"sanity:total_assets_less_than_equity:{val} < {eq}"
            )

    return ok


# ---------------------------------------------------------------------------
# Single-fact validation
# ---------------------------------------------------------------------------


def validate_candidate_fact(
    fact: CandidateFact,
    known_metric_ids: frozenset[str],
    allowed_period_types: frozenset[str] = frozenset({"FY"}),
    _peer_facts: Optional[list[CandidateFact]] = None,
) -> ValidationResult:
    """Run all validation rules on a single fact. Mutates fact.validation_status.

    Args:
        fact: The CandidateFact to validate.
        known_metric_ids: Set of known metric_ids loaded from the metric dictionary.
        allowed_period_types: Period types that are acceptable (default: only "FY").
        _peer_facts: Optional list of sibling facts for cross-metric sanity checks.
                     Callers should pass the full batch; validate_candidate_facts()
                     handles this automatically.

    Returns:
        ValidationResult with mutated fact.
    """
    failures: list[str] = []
    warnings: list[str] = []
    rules_applied: list[str] = []

    peer_facts = _peer_facts or []

    # Rule 1: schema
    rules_applied.append("schema")
    schema_ok = _rule_schema(fact, known_metric_ids, failures, warnings)

    # Rule 2: period
    rules_applied.append("period")
    period_ok = _rule_period(fact, allowed_period_types, failures, warnings)

    # Rule 3: financial sanity (only if schema and period passed to have a valid value)
    rules_applied.append("financial_sanity")
    sanity_ok = _rule_financial_sanity(fact, peer_facts, failures, warnings)

    passed = schema_ok and period_ok and sanity_ok
    fact.validation_status = "passed" if passed else "failed"

    # Merge any new warnings into the fact's warning list
    for w in warnings:
        if w not in fact.warnings:
            fact.warnings.append(w)

    return ValidationResult(
        fact=fact,
        passed=passed,
        rules_applied=rules_applied,
        failures=failures,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Batch validation (includes duplicate detection)
# ---------------------------------------------------------------------------


def _apply_duplicate_detection(
    facts: list[CandidateFact],
    results_by_id: dict[str, ValidationResult],
) -> None:
    """Rule 4 — Duplicate detection.

    Groups facts by (ticker, fiscal_year, period_type, statement_type, metric_id).
    Within each group:
    - If 2+ facts have different normalized_values → ALL marked "failed"
      with warning "duplicate_metric_conflict".
    - If all duplicates have same value (within 0.1%) → keep first, mark rest
      "failed" with warning "duplicate_metric_redundant".

    Mutates CandidateFact.validation_status and ValidationResult for affected facts.
    """
    # Build groups
    groups: dict[tuple, list[CandidateFact]] = {}
    for fact in facts:
        key = (
            fact.ticker,
            fact.fiscal_year,
            fact.period_type,
            fact.statement_type,
            fact.metric_id,
        )
        groups.setdefault(key, []).append(fact)

    for key, group in groups.items():
        if len(group) < 2:
            continue  # no duplicates

        try:
            values = [float(f.normalized_value) for f in group]
        except (TypeError, ValueError):
            # If any value is non-numeric, skip (already caught by schema)
            continue

        ref = values[0]
        all_same = all(
            abs(v - ref) / (abs(ref) + 1e-12) <= 0.001 for v in values
        )

        if all_same:
            # Keep the first, mark rest as redundant
            for fact in group[1:]:
                w = "duplicate_metric_redundant"
                if w not in fact.warnings:
                    fact.warnings.append(w)
                fact.validation_status = "failed"
                res = results_by_id.get(fact.candidate_fact_id)
                if res is not None:
                    res.passed = False
                    if w not in res.failures:
                        res.failures.append(w)
                    if "duplicate_detection" not in res.rules_applied:
                        res.rules_applied.append("duplicate_detection")
        else:
            # Values conflict — fail ALL
            for fact in group:
                w = "duplicate_metric_conflict"
                if w not in fact.warnings:
                    fact.warnings.append(w)
                fact.validation_status = "failed"
                res = results_by_id.get(fact.candidate_fact_id)
                if res is not None:
                    res.passed = False
                    if w not in res.failures:
                        res.failures.append(w)
                    if "duplicate_detection" not in res.rules_applied:
                        res.rules_applied.append("duplicate_detection")


def validate_candidate_facts(
    facts: list[CandidateFact],
    known_metric_ids: Optional[frozenset[str]] = None,
    allowed_period_types: frozenset[str] = frozenset({"FY"}),
) -> list[ValidationResult]:
    """Validate a list of facts. Applies all rules including cross-fact duplicate detection.

    If known_metric_ids is None, loads from config/financial_metric_dictionary.yaml.

    Args:
        facts: List of CandidateFact to validate (mutated in place).
        known_metric_ids: Optional frozenset of valid metric_ids.
                          If None, loaded from YAML at call time.
        allowed_period_types: Allowed period_type values (default: {"FY"}).

    Returns:
        List of ValidationResult, one per input fact, in the same order.
    """
    if known_metric_ids is None:
        known_metric_ids = load_known_metric_ids()

    # Rules 1–3: validate each fact, passing all facts as peers for cross-metric checks
    results: list[ValidationResult] = []
    for fact in facts:
        result = validate_candidate_fact(
            fact=fact,
            known_metric_ids=known_metric_ids,
            allowed_period_types=allowed_period_types,
            _peer_facts=facts,
        )
        results.append(result)

    # Rule 4: duplicate detection (cross-fact, may downgrade previously-passed facts)
    results_by_id = {r.fact.candidate_fact_id: r for r in results}
    _apply_duplicate_detection(facts, results_by_id)

    return results


# ---------------------------------------------------------------------------
# Required metric coverage check
# ---------------------------------------------------------------------------


def check_required_metric_coverage(
    facts: list[CandidateFact],
    required: dict[str, list[str]] = REQUIRED_METRICS,
) -> dict[str, list[str]]:
    """Return dict of statement_type -> list of missing metric_ids.

    Only considers facts with validation_status == "passed".
    Returns empty lists if all required metrics are present.

    Args:
        facts: List of CandidateFact (already validated).
        required: Dict mapping statement_type -> list of required metric_ids.
                  Defaults to REQUIRED_METRICS.

    Returns:
        Dict with same keys as `required`, each value being a list of
        metric_ids that are absent from the passed facts.
    """
    # Collect present metric_ids per statement_type from passed facts only
    present: dict[str, set[str]] = {}
    for fact in facts:
        if fact.validation_status == "passed":
            present.setdefault(fact.statement_type, set()).add(fact.metric_id)

    missing: dict[str, list[str]] = {}
    for stmt_type, metric_ids in required.items():
        have = present.get(stmt_type, set())
        missing[stmt_type] = [mid for mid in metric_ids if mid not in have]

    return missing
